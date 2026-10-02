"""Compiles a DRF serializer instance into a `fast_drf_core.CompiledSerializer`.

Every field is described for the Rust core either with a native kind or with `python`, in which
case the core calls the field's own methods. A field only gets a native kind when its class uses
the stock DRF implementation of every method the kind replaces, so subclasses that customise
behaviour keep working unchanged.
"""

import logging

from django.conf import settings
from django.core import validators as django_validators
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Field as DjangoModelField
from django.utils import timezone
from fast_drf_core import CompiledSerializer
from rest_framework import fields as drf_fields
from rest_framework import relations as drf_relations
from rest_framework import serializers as drf_serializers
from rest_framework.settings import api_settings
from rest_framework.validators import ProhibitSurrogateCharactersValidator

from . import _state

logger = logging.getLogger('fast_drf')

ISO_8601 = 'iso-8601'
CACHE_ATTR = '_fast_drf_compiled'
I64_MAX = 2**63 - 1
FLOAT_EXACT_LIMIT = 2**53

PYTHON = {'type': 'python'}

# Captured before `fast_drf.patch()` can replace the module attributes.
DRFSerializer = drf_serializers.Serializer
DRFListSerializer = drf_serializers.ListSerializer
DRF_SERIALIZER_TO_REPRESENTATION = DRFSerializer.to_representation
DRF_LIST_TO_REPRESENTATION = DRFListSerializer.to_representation


def get_compiled(serializer):
    """The compiled form of a serializer instance, cached on it; `None` when it cannot be compiled."""
    try:
        return serializer.__dict__[CACHE_ATTR]
    except KeyError:
        pass
    compiled = None
    if getattr(serializer, 'fast_drf', True):
        try:
            compiled = compile_serializer(serializer)
        except Exception:
            if _state.strict:
                raise
            logger.exception('fast_drf: cannot compile %s, using DRF', type(serializer).__name__)
    serializer.__dict__[CACHE_ATTR] = compiled
    return compiled


def current_timezone():
    return timezone.get_current_timezone() if settings.USE_TZ else None


def compile_serializer(serializer):
    model = getattr(getattr(serializer, 'Meta', None), 'model', None)
    read_fields = [
        {
            'name': field.field_name,
            'field': field,
            'get': get_spec(field, model),
            'repr': repr_spec(field, model),
        }
        for field in serializer._readable_fields
    ]
    write_fields = [write_spec(serializer, field) for field in serializer._writable_fields]
    return CompiledSerializer(read_fields, write_fields)


def is_stock(field, base, *methods):
    """`field` is an instance of `base` and does not override any of `methods`."""
    cls = type(field)
    return isinstance(field, base) and all(getattr(cls, name) is getattr(base, name) for name in methods)


def has_fast_representation(serializer):
    from .serializers import FastSerializerMixin

    method = type(serializer).to_representation
    return method is DRF_SERIALIZER_TO_REPRESENTATION or method is FastSerializerMixin.to_representation


def has_fast_validation(serializer):
    """`serializer.run_validation(item)` is equivalent to its compiled `to_internal_value(item)` for a dict item."""
    from .serializers import FastSerializerMixin

    cls = type(serializer)
    return (
        cls.to_internal_value in (FastSerializerMixin.to_internal_value, DRFSerializer.to_internal_value)
        and cls.run_validation is DRFSerializer.run_validation
        and cls.validate_empty_values is drf_fields.Field.validate_empty_values
        and cls.run_validators is DRFSerializer.run_validators
        and cls.validate is DRFSerializer.validate
        and not serializer.read_only
        and not serializer.validators
    )


def has_fast_list_representation(list_serializer):
    from .serializers import ListSerializer

    method = type(list_serializer).to_representation
    return method is DRF_LIST_TO_REPRESENTATION or method is ListSerializer.to_representation


# Reading: attribute access.


def get_spec(field, model):
    if pk_attname(field, model) is not None:
        return {'type': 'pk_attname', 'attname': pk_attname(field, model)}
    if model_field_attname(field) is not None:
        return {'type': 'star'}
    if type(field).get_attribute is not drf_fields.Field.get_attribute:
        return PYTHON
    if field.source == '*':
        return {'type': 'star'}
    return {'type': 'attrs', 'attrs': list(field.source_attrs)}


def is_plain_pk_field(field):
    return (
        is_stock(
            field,
            drf_relations.PrimaryKeyRelatedField,
            'get_attribute',
            'to_representation',
            'use_pk_only_optimization',
        )
        and field.pk_field is None
    )


def pk_attname(field, model):
    """`<fk>_id` for a `PrimaryKeyRelatedField` over a forward relation of the serializer's model."""
    if model is None or not is_plain_pk_field(field) or len(field.source_attrs) != 1:
        return None
    try:
        model_field = model._meta.get_field(field.source_attrs[0])
    except FieldDoesNotExist:
        return None
    if not (model_field.concrete and (model_field.many_to_one or model_field.one_to_one)):
        return None
    return model_field.attname


def model_field_attname(field):
    """`attname` for a stock `ModelField` whose model field reads a plain attribute."""
    if not is_stock(field, drf_fields.ModelField, 'get_attribute', 'to_representation'):
        return None
    if type(field.model_field).value_from_object is not DjangoModelField.value_from_object:
        return None
    return field.model_field.attname


# Reading: to_representation.


def repr_spec(field, model):
    if pk_attname(field, model) is not None:
        return {'type': 'pk'}
    if model_field_attname(field) is not None:
        return {'type': 'model_attr', 'attname': model_field_attname(field)}
    if isinstance(field, DRFListSerializer):
        return nested_repr_spec(field, many=True)
    if isinstance(field, drf_serializers.BaseSerializer):
        return nested_repr_spec(field, many=False)
    if isinstance(field, drf_relations.ManyRelatedField):
        if is_stock(field, drf_relations.ManyRelatedField, 'to_representation') and is_plain_pk_field(
            field.child_relation
        ):
            return {'type': 'pk_many'}
        return PYTHON
    return leaf_repr_spec(field)


def nested_repr_spec(field, many):
    child = field.child if many else field
    if many and not has_fast_list_representation(field):
        return PYTHON
    if not isinstance(child, DRFSerializer) or not has_fast_representation(child):
        return PYTHON
    compiled = get_compiled(child)
    if compiled is None:
        return PYTHON
    return {'type': 'nested', 'serializer': compiled, 'many': many}


def leaf_repr_spec(field):
    f = drf_fields
    if is_stock(field, f.SerializerMethodField, 'to_representation'):
        return {'type': 'method', 'method': getattr(field.parent, field.method_name)}
    if is_stock(field, f.ReadOnlyField, 'to_representation'):
        return {'type': 'passthrough'}
    if is_stock(field, f.JSONField, 'to_representation') and not field.binary:
        return {'type': 'passthrough'}
    if is_stock(field, f.CharField, 'to_representation'):
        return {'type': 'str'}
    if is_stock(field, f.IntegerField, 'to_representation'):
        return {'type': 'int'}
    if is_stock(field, f.FloatField, 'to_representation'):
        return {'type': 'float'}
    if is_stock(field, f.BooleanField, 'to_representation'):
        return {'type': 'bool'}
    if is_stock(field, f.DecimalField, 'to_representation', 'quantize'):
        if field.localize:
            return PYTHON
        return {
            'type': 'decimal',
            'decimal_places': field.decimal_places,
            'max_digits': field.max_digits,
            'coerce_to_string': bool(getattr(field, 'coerce_to_string', api_settings.COERCE_DECIMAL_TO_STRING)),
        }
    if is_stock(field, f.DateTimeField, 'to_representation', 'enforce_timezone', 'default_timezone'):
        output_format = getattr(field, 'format', api_settings.DATETIME_FORMAT)
        if output_format is None:
            return {'type': 'passthrough'}
        if output_format.lower() != ISO_8601:
            return PYTHON
        if hasattr(field, 'timezone'):
            return {'type': 'datetime', 'timezone': field.timezone}
        return {'type': 'datetime', 'use_tz': settings.USE_TZ}
    for field_class, kind, setting in (
        (f.DateField, 'date', 'DATE_FORMAT'),
        (f.TimeField, 'time', 'TIME_FORMAT'),
    ):
        if is_stock(field, field_class, 'to_representation'):
            output_format = getattr(field, 'format', getattr(api_settings, setting))
            if output_format is None:
                return {'type': 'passthrough'}
            return {'type': kind} if output_format.lower() == ISO_8601 else PYTHON
    if is_stock(field, f.UUIDField, 'to_representation'):
        return {'type': 'uuid'} if field.uuid_format == 'hex_verbose' else PYTHON
    if is_stock(field, f.ChoiceField, 'to_representation') and not isinstance(field, f.MultipleChoiceField):
        return {'type': 'choice', 'map': field.choice_strings_to_values}
    if is_stock(field, f.ListField, 'to_representation'):
        return {'type': 'list', 'child': leaf_repr_spec(field.child), 'child_field': field.child}
    if is_stock(field, f.DictField, 'to_representation'):
        return {'type': 'dict', 'child': leaf_repr_spec(field.child), 'child_field': field.child}
    return PYTHON


# Writing: to_internal_value.

VALIDATION_METHODS = ('get_value', 'validate_empty_values', 'run_validation', 'to_internal_value', 'run_validators')


def write_spec(serializer, field):
    val, python_validators = val_spec(field)
    return {
        'name': field.field_name,
        'field': field,
        'source_attrs': list(field.source_attrs),
        'validate_method': getattr(serializer, 'validate_' + field.field_name, None),
        'allow_null': field.allow_null,
        'python_validators': python_validators,
        'val': val,
    }


def val_spec(field):
    """`(val, python_validators)`: the native kind and whether some validators must run in Python."""
    f = drf_fields
    if is_stock(field, f.CharField, *VALIDATION_METHODS):
        limits, rest = split_validators(field.validators, char_validator_limits)
        return {
            'type': 'char',
            'allow_blank': field.allow_blank,
            'trim_whitespace': field.trim_whitespace,
            'max_length': limits.get('max'),
            'min_length': limits.get('min'),
            'email': 'email' in limits,
        }, rest
    if isinstance(field, drf_serializers.BaseSerializer):
        return nested_val_spec(field), False
    if is_stock(field, f.IntegerField, *VALIDATION_METHODS):
        limits, rest = split_validators(field.validators, value_limits(int, lambda v: -I64_MAX <= v <= I64_MAX))
        return {'type': 'int', 'max_value': limits.get('max'), 'min_value': limits.get('min')}, rest
    if is_stock(field, f.FloatField, *VALIDATION_METHODS):
        limits, rest = split_validators(
            field.validators, value_limits((int, float), lambda v: abs(v) <= FLOAT_EXACT_LIMIT)
        )
        return {'type': 'float', 'max_value': limits.get('max'), 'min_value': limits.get('min')}, rest
    if is_stock(field, f.BooleanField, *VALIDATION_METHODS):
        return {'type': 'bool', 'allow_null': field.allow_null}, bool(field.validators)
    if is_stock(field, f.DecimalField, *VALIDATION_METHODS, 'validate_precision', 'quantize') and not field.localize:
        return {
            'type': 'decimal',
            'max_digits': field.max_digits,
            'decimal_places': field.decimal_places,
        }, bool(field.validators)
    if is_stock(field, f.DateField, *VALIDATION_METHODS):
        input_formats = getattr(field, 'input_formats', api_settings.DATE_INPUT_FORMATS)
        if [str(fmt).lower() for fmt in input_formats] == [ISO_8601]:
            return {'type': 'date'}, bool(field.validators)
        return PYTHON, False
    if is_stock(field, f.DateTimeField, *VALIDATION_METHODS, 'enforce_timezone', 'default_timezone'):
        input_formats = getattr(field, 'input_formats', api_settings.DATETIME_INPUT_FORMATS)
        if [str(fmt).lower() for fmt in input_formats] != [ISO_8601]:
            return PYTHON, False
        if hasattr(field, 'timezone'):
            return {'type': 'datetime', 'timezone': field.timezone}, bool(field.validators)
        return {'type': 'datetime', 'use_tz': settings.USE_TZ}, bool(field.validators)
    if is_stock(field, f.UUIDField, *VALIDATION_METHODS):
        return {'type': 'uuid'}, bool(field.validators)
    if is_stock(field, f.ChoiceField, *VALIDATION_METHODS) and not isinstance(field, f.MultipleChoiceField):
        return {
            'type': 'choice',
            'map': field.choice_strings_to_values,
            'allow_blank': field.allow_blank,
        }, bool(field.validators)
    if is_stock(field, f.ListField, *VALIDATION_METHODS, 'run_child_validation'):
        child_val, child_python_validators = val_spec(field.child)
        if child_val['type'] == 'python' or child_python_validators:
            return PYTHON, False
        limits, rest = split_validators(field.validators, list_validator_limits)
        return {
            'type': 'list',
            'child': child_val,
            'child_allow_null': field.child.allow_null,
            'allow_empty': field.allow_empty,
            'max_length': limits.get('max'),
            'min_length': limits.get('min'),
        }, rest
    return PYTHON, False


def nested_val_spec(field):
    if isinstance(field, DRFListSerializer):
        cls = type(field)
        stock = (
            cls.run_validation is DRFListSerializer.run_validation
            and cls.to_internal_value in list_to_internal_value_methods()
            and cls.get_value is DRFListSerializer.get_value
            and cls.validate_empty_values is drf_fields.Field.validate_empty_values
            and cls.run_validators is drf_fields.Field.run_validators
            and cls.validate is DRFListSerializer.validate
            and getattr(cls, 'run_child_validation', None) is getattr(DRFListSerializer, 'run_child_validation', None)
            and not field.validators
        )
        child = field.child
        if not stock or not isinstance(child, DRFSerializer) or not has_fast_validation(child):
            return PYTHON
        compiled = get_compiled(child)
        if compiled is None:
            return PYTHON
        return {
            'type': 'nested',
            'many': True,
            'serializer': compiled,
            'allow_empty': field.allow_empty,
            'max_length': getattr(field, 'max_length', None),
            'min_length': getattr(field, 'min_length', None),
        }
    if (
        isinstance(field, DRFSerializer)
        and type(field).get_value is DRFSerializer.get_value
        and has_fast_validation(field)
        and get_compiled(field) is not None
    ):
        return {'type': 'nested', 'serializer': get_compiled(field)}
    return PYTHON


def list_to_internal_value_methods():
    from .serializers import ListSerializer

    return (DRFListSerializer.to_internal_value, ListSerializer.to_internal_value)


def split_validators(validators, classify):
    """Merges the validators the core checks natively into `{'max': .., 'min': ..}` limits.
    Returns the limits and whether any other validator is left for Python."""
    limits = {}
    rest = False
    for validator in validators:
        kind = classify(validator)
        if kind is None:
            rest = True
        elif kind[0] == 'max':
            limits['max'] = kind[1] if 'max' not in limits else min(limits['max'], kind[1])
        elif kind[0] == 'min':
            limits['min'] = kind[1] if 'min' not in limits else max(limits['min'], kind[1])
        elif kind[0] == 'email':
            limits['email'] = True
    return limits, rest


def plain_int(value):
    return type(value) is int


def char_validator_limits(validator):
    cls = type(validator)
    if cls is django_validators.ProhibitNullCharactersValidator or cls is ProhibitSurrogateCharactersValidator:
        return ('noop', None)
    if cls is django_validators.MaxLengthValidator and plain_int(validator.limit_value):
        return ('max', validator.limit_value)
    if cls is django_validators.MinLengthValidator and plain_int(validator.limit_value):
        return ('min', validator.limit_value)
    if is_stock_email_validator(validator):
        return ('email', True)
    return None


def is_stock_email_validator(validator):
    """Django's `EmailValidator` with its own regexes; the core accepts a strict subset of what it does
    (a custom `allowlist` only widens what Django accepts)."""
    cls = django_validators.EmailValidator
    return (
        type(validator) is cls and validator.user_regex is cls.user_regex and validator.domain_regex is cls.domain_regex
    )


def list_validator_limits(validator):
    cls = type(validator)
    if cls is django_validators.MaxLengthValidator and plain_int(validator.limit_value):
        return ('max', validator.limit_value)
    if cls is django_validators.MinLengthValidator and plain_int(validator.limit_value):
        return ('min', validator.limit_value)
    return None


def value_limits(types, in_range):
    types = types if isinstance(types, tuple) else (types,)

    def classify(validator):
        cls = type(validator)
        limit = getattr(validator, 'limit_value', None)
        if type(limit) not in types or not in_range(limit):
            return None
        if cls is django_validators.MaxValueValidator:
            return ('max', limit)
        if cls is django_validators.MinValueValidator:
            return ('min', limit)
        return None

    return classify
