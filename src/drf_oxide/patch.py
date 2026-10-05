"""Swap DRF's classes for the fast ones, so existing code gets faster without import changes.

Call `drf_oxide.patch()` before your serializers are imported, e.g. at the end of settings or at the
top of the root `urls.py`. Classes defined before the call keep subclassing the DRF originals.
"""

import warnings

_patched = False


def patch():
    global _patched
    if _patched:
        return
    from rest_framework import parsers, renderers, serializers

    too_early = sorted(
        f'{cls.__module__}.{cls.__qualname__}'
        for cls in _subclasses(serializers.BaseSerializer)
        if not cls.__module__.startswith(('rest_framework.', 'drf_oxide.'))
    )
    if too_early:
        warnings.warn(
            f'drf_oxide.patch() was called after these serializers were defined, they keep using DRF: '
            f'{", ".join(too_early)}',
            stacklevel=2,
        )

    from . import parsers as fast_parsers
    from . import renderers as fast_renderers
    from . import serializers as fast_serializers

    for name in ('Serializer', 'ModelSerializer', 'HyperlinkedModelSerializer', 'ListSerializer'):
        setattr(serializers, name, getattr(fast_serializers, name))
    renderers.JSONRenderer = fast_renderers.JSONRenderer
    parsers.JSONParser = fast_parsers.JSONParser
    _patched = True


def _subclasses(cls):
    for subclass in cls.__subclasses__():
        yield subclass
        yield from _subclasses(subclass)
