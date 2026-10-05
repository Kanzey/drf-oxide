# fast-drf

Drop-in, Rust-accelerated serializers, JSON renderer and JSON parser for Django REST framework.
The Rust part lives in [`fast-drf-core`](../fast-drf-core), the same way pydantic sits on pydantic-core.

```python
from fast_drf import serializers          # instead of: from rest_framework import serializers


class BookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = '__all__'
```

```python
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': ['fast_drf.renderers.JSONRenderer'],
    'DEFAULT_PARSER_CLASSES': ['fast_drf.parsers.JSONParser'],
}
```

Or, without touching imports, call `fast_drf.patch()` before serializers are imported.

## How it works

Each serializer instance is compiled once: every field gets a native kind when its class uses the stock
DRF implementation, otherwise the core calls the field's own Python methods. Native code only handles the
plain, valid case; anything unusual (an error, an odd input type, a value that needs rounding) is handed
back to DRF, so output and error messages stay identical.

Django relations that are already loaded (`select_related`, `prefetch_related`) are read straight from
the instance caches, skipping the relation descriptors and the related managers; anything not cached goes
through the descriptor as usual.

`ModelSerializer` works out its model fields (model introspection, field classes and kwargs) once per
serializer class, language and settings, instead of on every instance as DRF does, as long as the class
keeps DRF's stock field-building methods. Every instance still gets its own field objects.

- `fast_drf.disabled()` runs plain DRF inside the block.
- `fast_drf = False` on a serializer class opts it out.

## Speed

`make bench` (1000 rows, 15 fields incl. a nested serializer, Python 3.13, release build):

| | DRF | fast-drf | |
|---|---|---|---|
| `Serializer(many=True).data` | 42.6 ms | 8.8 ms | 4.9x |
| `is_valid()` on a list payload | 131.8 ms | 12.2 ms | 10.8x |
| `JSONRenderer.render` | 5.2 ms | 2.2 ms | 2.4x |

Per field kind, serialization is ~10x for strings, ints, bools, decimals and choices; datetimes in a
non-UTC active timezone and UUIDs gain less (~4x / ~2.5x).

## Development

```sh
cd ../fast-drf-core && make develop   # or `make release` for benchmarks
cd ../fast-drf && uv sync && make test
make bench
```
