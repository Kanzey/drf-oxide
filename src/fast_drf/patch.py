"""Swap DRF's classes for the fast ones, so existing code gets faster without import changes.

Call `fast_drf.patch()` before your serializers are imported, e.g. at the end of settings or at the
top of the root `urls.py`. Classes defined before the call keep subclassing the DRF originals.
"""

_patched = False


def patch():
    global _patched
    if _patched:
        return
    from rest_framework import parsers, renderers, serializers

    from . import parsers as fast_parsers
    from . import renderers as fast_renderers
    from . import serializers as fast_serializers

    for name in ('Serializer', 'ModelSerializer', 'HyperlinkedModelSerializer', 'ListSerializer'):
        setattr(serializers, name, getattr(fast_serializers, name))
    renderers.JSONRenderer = fast_renderers.JSONRenderer
    parsers.JSONParser = fast_parsers.JSONParser
    _patched = True
