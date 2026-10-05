from drf_oxide_core import JsonFallback, to_json
from rest_framework import renderers as _drf
from rest_framework.renderers import *  # noqa: F403
from rest_framework.utils.encoders import JSONEncoder

from . import _state

_DEFAULT = JSONEncoder().default


class JSONRenderer(_drf.JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return b''
        if not _state.enabled or self.encoder_class is not JSONEncoder:
            return super().render(data, accepted_media_type, renderer_context)
        if self.get_indent(accepted_media_type, renderer_context or {}) is not None:
            return super().render(data, accepted_media_type, renderer_context)
        try:
            return to_json(
                data,
                ensure_ascii=self.ensure_ascii,
                compact=self.compact,
                allow_nan=not self.strict,
                default=_DEFAULT,
            )
        except JsonFallback:
            return super().render(data, accepted_media_type, renderer_context)
