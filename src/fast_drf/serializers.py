"""Drop-in replacement for `rest_framework.serializers`.

`from fast_drf import serializers` gives the same names as `from rest_framework import serializers`;
`Serializer`, `ModelSerializer`, `HyperlinkedModelSerializer` and `ListSerializer` run their
`to_representation` / `to_internal_value` loops in Rust.
"""

from django.db import models
from rest_framework import serializers as _drf
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import *  # noqa: F403

from . import _runtime, _state
from ._compiler import current_timezone, get_compiled, has_fast_representation, has_fast_validation
from ._model_fields import cached_model_fields

_runtime.configure()

DRFSerializer = _drf.Serializer
DRFModelSerializer = _drf.ModelSerializer
DRFHyperlinkedModelSerializer = _drf.HyperlinkedModelSerializer
DRFListSerializer = _drf.ListSerializer


class FastSerializerMixin:
    """Set `fast_drf = False` on a serializer class to always use the DRF implementation."""

    fast_drf = True

    @classmethod
    def many_init(cls, *args, **kwargs):
        list_serializer = super().many_init(*args, **kwargs)
        if type(list_serializer) is DRFListSerializer:
            list_serializer.__class__ = ListSerializer
        return list_serializer

    def to_representation(self, instance):
        compiled = get_compiled(self) if _state.enabled else None
        if compiled is None:
            return super().to_representation(instance)
        return compiled.to_representation(instance, current_timezone())

    def to_internal_value(self, data):
        compiled = get_compiled(self) if _state.enabled and type(data) is dict else None
        if compiled is None:
            return super().to_internal_value(data)
        ret, errors = compiled.to_internal_value(data, current_timezone())
        if errors:
            raise ValidationError(errors)
        return ret


class Serializer(FastSerializerMixin, DRFSerializer):
    pass


class FastModelSerializerMixin(FastSerializerMixin):
    def get_fields(self):
        fields = cached_model_fields(self) if _state.enabled else None
        if fields is None:
            return super().get_fields()
        return fields


# The fast classes keep DRF's hierarchy (ModelSerializer is a Serializer, ...), so that after
# `fast_drf.patch()` `isinstance(x, serializers.Serializer)` holds for every serializer as before.
class ModelSerializer(FastModelSerializerMixin, DRFModelSerializer, Serializer):
    pass


class HyperlinkedModelSerializer(DRFHyperlinkedModelSerializer, ModelSerializer):
    pass


# DRF >= 3.15 lets subclasses customise per-item validation (e.g. for multiple updates).
_DRF_RUN_CHILD_VALIDATION = getattr(DRFListSerializer, 'run_child_validation', None)


class ListSerializer(DRFListSerializer):
    def to_representation(self, data):
        child = self.child
        compiled = (
            get_compiled(child)
            if _state.enabled and isinstance(child, DRFSerializer) and has_fast_representation(child)
            else None
        )
        if compiled is None:
            return super().to_representation(data)
        iterable = data.all() if isinstance(data, models.Manager) else data
        return compiled.to_representation_many(iterable, current_timezone())

    def to_internal_value(self, data):
        child = self.child
        compiled = (
            get_compiled(child)
            if _state.enabled
            and type(data) is list
            and getattr(type(self), 'run_child_validation', None) is _DRF_RUN_CHILD_VALIDATION
            and has_fast_validation(child)
            else None
        )
        length = len(data) if compiled is not None else 0
        if (
            compiled is None
            or (not self.allow_empty and length == 0)
            or (self.max_length is not None and length > self.max_length)
            or (self.min_length is not None and length < self.min_length)
        ):
            return super().to_internal_value(data)

        # DRF's loop, with `child.run_validation(item)` short-circuited for dict items.
        current_tz = current_timezone()
        ret = []
        errors = []
        for item in data:
            if type(item) is dict:
                validated, item_errors = compiled.to_internal_value(item, current_tz)
                if item_errors:
                    errors.append(ValidationError(item_errors).detail)
                    continue
            else:
                try:
                    validated = child.run_validation(item)
                except ValidationError as exc:
                    errors.append(exc.detail)
                    continue
            ret.append(validated)
            errors.append({})

        if any(errors):
            raise ValidationError(errors)
        return ret
