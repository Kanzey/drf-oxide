from collections.abc import Mapping

from rest_framework.exceptions import ErrorDetail

import drf_oxide


def assert_identical(actual, expected, path='$'):
    """Equal values *and* equal types all the way down (dict vs OrderedDict, ErrorDetail codes)."""
    assert type(actual) is type(expected), f'{path}: {type(actual).__name__} != {type(expected).__name__}'
    if isinstance(expected, Mapping):
        assert list(actual) == list(expected), f'{path}: keys {list(actual)} != {list(expected)}'
        for key in expected:
            assert_identical(actual[key], expected[key], f'{path}.{key}')
    elif isinstance(expected, (list, tuple)):
        assert len(actual) == len(expected), f'{path}: len {len(actual)} != {len(expected)}'
        for index, (a, e) in enumerate(zip(actual, expected, strict=True)):
            assert_identical(a, e, f'{path}[{index}]')
    elif isinstance(expected, ErrorDetail):
        assert (str(actual), actual.code) == (str(expected), expected.code), path
    else:
        assert actual == expected, f'{path}: {actual!r} != {expected!r}'


def compare(make):
    """Runs `make()` with DRF and with drf_oxide and checks both give the same result."""
    with drf_oxide.disabled():
        expected = make()
    actual = make()
    assert_identical(actual, expected)
    return actual


def validate(serializer_class, data, **kwargs):
    def make():
        serializer = serializer_class(data=data, **kwargs)
        if serializer.is_valid():
            return True, serializer.validated_data
        return False, serializer.errors

    return compare(make)
