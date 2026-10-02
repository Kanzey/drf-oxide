"""Python callbacks for the Rust core and its one-time configuration."""

from collections import OrderedDict

import fast_drf_core
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from fast_drf_core import STATUS_ERROR, STATUS_OK, STATUS_SKIP
from rest_framework import VERSION
from rest_framework.exceptions import ValidationError
from rest_framework.fields import SkipField, empty, get_error_detail, is_simple_callable
from rest_framework.relations import PKOnlyObject

# DRF 3.15 switched serializer output and errors from OrderedDict to dict.
DICT_FACTORY = OrderedDict if tuple(int(part) for part in VERSION.split('.')[:2]) < (3, 15) else dict


def resolve_callable(value, attr):
    """The callable branch of `rest_framework.fields.get_attribute`."""
    if is_simple_callable(value):
        try:
            return value()
        except (AttributeError, KeyError) as exc:
            raise ValueError(f'Exception raised in callable attribute "{attr}"; original exception was: {exc}') from exc
    return value


def run_field(field, data, validate_method):
    """One iteration of the field loop in `Serializer.to_internal_value`."""
    primitive_value = field.get_value(data)
    try:
        validated_value = field.run_validation(primitive_value)
        if validate_method is not None:
            validated_value = validate_method(validated_value)
    except ValidationError as exc:
        return STATUS_ERROR, exc.detail
    except DjangoValidationError as exc:
        return STATUS_ERROR, get_error_detail(exc)
    except SkipField:
        return STATUS_SKIP, None
    return STATUS_OK, validated_value


def finish_field(field, value, validate_method, run_validators):
    """The rest of that iteration once `to_internal_value` succeeded in Rust."""
    try:
        if run_validators:
            field.run_validators(value)
        if validate_method is not None:
            value = validate_method(value)
    except ValidationError as exc:
        return STATUS_ERROR, exc.detail
    except DjangoValidationError as exc:
        return STATUS_ERROR, get_error_detail(exc)
    except SkipField:
        return STATUS_SKIP, None
    return STATUS_OK, value


def configure():
    if fast_drf_core.is_configured():
        return
    fast_drf_core.configure(
        empty=empty,
        skip_field=SkipField,
        object_does_not_exist=ObjectDoesNotExist,
        pk_only_object=PKOnlyObject,
        manager_class=models.Manager,
        dict_factory=DICT_FACTORY,
        resolve_callable=resolve_callable,
        run_field=run_field,
        finish_field=finish_field,
    )
