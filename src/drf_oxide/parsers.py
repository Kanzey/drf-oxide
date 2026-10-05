import codecs
import io

from django.conf import settings
from drf_oxide_core import from_json
from rest_framework import parsers as _drf
from rest_framework.parsers import *  # noqa: F403

from . import _state


class JSONParser(_drf.JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        encoding = (parser_context or {}).get('encoding', settings.DEFAULT_CHARSET)
        if not _state.enabled or codecs.lookup(encoding).name != 'utf-8':
            return super().parse(stream, media_type, parser_context)
        raw = stream.read()
        try:
            return from_json(raw, allow_nan=not self.strict)
        except ValueError:
            # Let the json module produce DRF's exact error message (or accept what jiter rejects).
            return super().parse(io.BytesIO(raw), media_type, parser_context)
