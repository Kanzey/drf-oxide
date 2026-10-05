"""`ModelSerializer.get_fields()` with the model introspection done once per serializer class.

DRF rebuilds every model field from scratch for every serializer instance: it walks the model meta,
works out the field class and its kwargs, and instantiates it. Only the last step depends on the
instance, so the rest is recorded once as a "recipe" of `(field_name, field_class, kwargs)` and
replayed. This is only done for classes that keep the stock DRF implementation of every method
involved, so the recipe is a pure function of the class, the active language (labels come from
translated verbose names) and the settings.
"""

import contextvars
import copy

from django.core.signals import setting_changed
from django.utils import translation
from rest_framework import serializers as drf_serializers
from rest_framework.fields import Field
from rest_framework.settings import api_settings
from rest_framework.utils import model_meta

from ._runtime import DICT_FACTORY

DRFModelSerializer = drf_serializers.ModelSerializer
DRFHyperlinkedModelSerializer = drf_serializers.HyperlinkedModelSerializer

BUILD_METHODS = (
    'get_field_names',
    'get_default_field_names',
    'get_extra_kwargs',
    'get_uniqueness_extra_kwargs',
    'include_extra_kwargs',
    'build_field',
    'build_standard_field',
    'build_relational_field',
    'build_nested_field',
    'build_property_field',
    'build_url_field',
    'build_unknown_field',
    '_get_model_fields',
    'get_unique_together_constraints',
)
# Class attributes the build methods read; set on an instance they make the result instance-specific.
BUILD_ATTRIBUTES = (
    'Meta',
    'serializer_field_mapping',
    'serializer_related_field',
    'serializer_related_to_field',
    'serializer_url_field',
    'serializer_choice_field',
)

_recipes = {}

# `(language,)` while a serializer tree is being compiled, see `_compiler.get_compiled()`.
compile_language = contextvars.ContextVar('drf_oxide_compile_language', default=None)


def _clear(**kwargs):
    _recipes.clear()


setting_changed.connect(_clear)


def cached_model_fields(serializer):
    """The result of DRF's `ModelSerializer.get_fields()`, or `None` if it cannot be cached."""
    if serializer.url_field_name is None:
        serializer.url_field_name = api_settings.URL_FIELD_NAME
    language = compile_language.get()
    language = translation.get_language() if language is None else language[0]
    key = (type(serializer), language, serializer.url_field_name)
    recipe = _recipes.get(key)
    if recipe is None:
        if not is_cacheable(serializer):
            return None
        recipe = _recipes[key] = build_recipe(serializer)

    declared_fields = copy.deepcopy(serializer._declared_fields)
    fields = DICT_FACTORY()
    for field_name, spec in recipe:
        fields[field_name] = declared_fields[field_name] if spec is None else instantiate(*spec)
    return fields


def instantiate(field_class, field_kwargs, prototype):
    """`field_class(**field_kwargs)`. With a prototype (the same call, made once), a copy of it instead:
    `__init__` is deterministic for these kwargs, and some of it is costly (e.g. flattening large
    `choices`). Containers are copied so that changing one instance's validators, error messages
    or choices does not leak into the others."""
    if prototype is None:
        return field_class(**{key: fresh(value) for key, value in field_kwargs.items()})
    field = object.__new__(field_class)
    field.__dict__.update(
        {
            key: value.copy() if isinstance(value, (list, dict, set)) else value
            for key, value in prototype.__dict__.items()
        }
    )
    return field


def make_prototype(field_class, field_kwargs):
    prototype = field_class(**{key: fresh(value) for key, value in field_kwargs.items()})
    # `many=True` relations come back as a different class; nested fields are bound to their parent.
    if type(prototype) is not field_class or any(isinstance(value, Field) for value in vars(prototype).values()):
        return None
    return prototype


def fresh(value):
    # A field instance (e.g. the `child` of a ListField) belongs to one parent; everything else is
    # shared, as DRF itself shares validators when copying declared fields.
    return copy.deepcopy(value) if isinstance(value, Field) else value


def is_cacheable(serializer):
    cls = type(serializer)
    for name in BUILD_METHODS:
        method = getattr(cls, name, None)
        if method is not getattr(DRFModelSerializer, name, None) and method is not getattr(
            DRFHyperlinkedModelSerializer, name, None
        ):
            return False
    return not any(name in serializer.__dict__ for name in BUILD_ATTRIBUTES)


def build_recipe(serializer):
    """DRF's `ModelSerializer.get_fields()`, recording what it instantiates instead of doing it."""
    assert hasattr(serializer, 'Meta'), f'Class {serializer.__class__.__name__} missing "Meta" attribute'
    assert hasattr(serializer.Meta, 'model'), f'Class {serializer.__class__.__name__} missing "Meta.model" attribute'
    if model_meta.is_abstract_model(serializer.Meta.model):
        raise ValueError('Cannot use ModelSerializer with Abstract Models.')

    declared_fields = copy.deepcopy(serializer._declared_fields)
    model = serializer.Meta.model
    depth = getattr(serializer.Meta, 'depth', 0)
    if depth is not None:
        assert depth >= 0, "'depth' may not be negative."
        assert depth <= 10, "'depth' may not be greater than 10."

    info = model_meta.get_field_info(model)
    field_names = serializer.get_field_names(declared_fields, info)
    extra_kwargs = serializer.get_extra_kwargs()
    extra_kwargs, hidden_fields = serializer.get_uniqueness_extra_kwargs(field_names, declared_fields, extra_kwargs)

    recipe = []
    for field_name in field_names:
        if field_name in declared_fields:
            recipe.append((field_name, None))
            continue
        extra_field_kwargs = extra_kwargs.get(field_name, {})
        source = extra_field_kwargs.get('source', '*')
        if source == '*':
            source = field_name
        field_class, field_kwargs = serializer.build_field(source, info, model, depth)
        field_kwargs = serializer.include_extra_kwargs(field_kwargs, extra_field_kwargs)
        recipe.append((field_name, (field_class, field_kwargs, make_prototype(field_class, field_kwargs))))

    for field_name, field in hidden_fields.items():
        assert not field._args, 'hidden fields are built with keyword arguments only'
        field_kwargs = dict(field._kwargs)
        recipe.append((field_name, (type(field), field_kwargs, make_prototype(type(field), field_kwargs))))
    return tuple(recipe)
