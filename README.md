# drf-oxide

Drop-in, Rust-accelerated serializers, JSON renderer and JSON parser for Django REST framework.
The Rust part lives in [`drf-oxide-core`](https://pypi.org/project/drf-oxide-core/), the same way pydantic
sits on pydantic-core.

```sh
pip install drf-oxide
```

Supports Python 3.10–3.14, Django 4.2–5.2 and Django REST framework 3.14–3.16.

## Usage

```python
from drf_oxide import serializers          # instead of: from rest_framework import serializers


class BookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = '__all__'
```

```python
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': ['drf_oxide.renderers.JSONRenderer'],
    'DEFAULT_PARSER_CLASSES': ['drf_oxide.parsers.JSONParser'],
}
```

Or, without touching imports, put `drf_oxide` first in `INSTALLED_APPS`: it swaps DRF's
`Serializer`, `ModelSerializer`, `HyperlinkedModelSerializer`, `ListSerializer`, `JSONRenderer` and
`JSONParser` for the fast ones before any other app imports its serializers.

```python
INSTALLED_APPS = ['drf_oxide', *INSTALLED_APPS]
```

`drf_oxide.patch()` does the same from code; it has to run before the serializers are defined.

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

- `drf_oxide.disabled()` runs plain DRF inside the block.
- `drf_oxide = False` on a serializer class opts it out.

## Speed

`make bench` (1000 rows, 15 fields incl. a nested serializer, Python 3.13, release build):

| | DRF | drf-oxide | |
|---|---|---|---|
| `Serializer(many=True).data` | 42.6 ms | 8.8 ms | 4.9x |
| `is_valid()` on a list payload | 131.8 ms | 12.2 ms | 10.8x |
| `JSONRenderer.render` | 5.2 ms | 2.2 ms | 2.4x |

Per field kind, serialization is ~10x for strings, ints, bools, decimals and choices; datetimes in a
non-UTC active timezone and UUIDs gain less (~4x / ~2.5x).

## Development

The two packages live in sibling checkouts of
[Kanzey/drf-oxide](https://github.com/Kanzey/drf-oxide) and
[Kanzey/drf-oxide-core](https://github.com/Kanzey/drf-oxide-core); `uv sync` installs the core from
`../drf-oxide-core`.

```sh
cd ../drf-oxide-core && make develop   # or `make release` for benchmarks
cd ../drf-oxide && uv sync && make test
make bench
```
