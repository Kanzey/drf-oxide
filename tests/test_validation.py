import datetime

import pytest
from django.core.validators import RegexValidator
from rest_framework.exceptions import ValidationError

from fast_drf import serializers
from fast_drf._compiler import get_compiled
from tests.utils import validate


class ChildSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)


class InputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=10, min_length=2)
    blank = serializers.CharField(allow_blank=True, required=False)
    untrimmed = serializers.CharField(trim_whitespace=False, required=False)
    email = serializers.EmailField(required=False)
    code = serializers.CharField(validators=[RegexValidator(r'^[A-Z]+$')], required=False)
    count = serializers.IntegerField(min_value=0, max_value=100, required=False)
    ratio = serializers.FloatField(required=False, max_value=1.5)
    flag = serializers.BooleanField(required=False)
    maybe = serializers.BooleanField(allow_null=True, required=False)
    price = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    loose = serializers.DecimalField(max_digits=None, decimal_places=None, required=False)
    day = serializers.DateField(required=False)
    when = serializers.DateTimeField(required=False)
    kind = serializers.ChoiceField(choices=[(1, 'one'), ('b', 'bee')], required=False)
    ident = serializers.UUIDField(required=False)
    tags = serializers.ListField(child=serializers.CharField(max_length=3), required=False, max_length=3)
    numbers = serializers.ListField(child=serializers.IntegerField(allow_null=True), required=False)
    nullable = serializers.CharField(allow_null=True, required=False)
    default = serializers.IntegerField(default=7)
    renamed = serializers.CharField(source='target.inner', required=False)
    child = ChildSerializer(required=False)
    children = ChildSerializer(many=True, required=False)
    hidden = serializers.HiddenField(default='hidden')
    read_only = serializers.CharField(read_only=True)

    def validate_count(self, value):
        if value == 13:
            raise ValidationError('unlucky', code='unlucky')
        return value * 2


VALID = {'name': 'Ala'}


def test_native_kinds():
    write = get_compiled(InputSerializer()).describe()['write']
    assert write == {
        'name': ('char', False),
        'blank': ('char', False),
        'untrimmed': ('char', False),
        'email': ('char', False),
        'code': ('char', True),
        'count': ('int', False),
        'ratio': ('float', False),
        'flag': ('bool', False),
        'maybe': ('bool', False),
        'price': ('decimal', False),
        'loose': ('decimal', False),
        'day': ('date', False),
        'when': ('datetime', False),
        'kind': ('choice', False),
        'ident': ('uuid', False),
        'tags': ('list[char]', False),
        'numbers': ('list[int]', False),
        'nullable': ('char', False),
        'default': ('int', False),
        'renamed': ('char', False),
        'child': ('nested', False),
        'children': ('nested_many', False),
        'hidden': ('python', False),
    }


@pytest.mark.parametrize(
    'payload',
    [
        {'name': 'Ala'},
        {'name': '  Ala  ', 'blank': '', 'untrimmed': '  x  '},
        {'name': ''},
        {'name': '   '},
        {'name': None},
        {'name': 'a'},
        {'name': 'abcdefghijkl'},
        {'name': 12},
        {'name': True},
        {'name': ['x']},
        {'name': 'a\x00b'},
        {'name': 'a\ud800'},
        {'email': 'not-an-email'},
        {'email': 'ok@example.com'},
        {'email': 'user@localhost'},
        {'email': '"quoted"@example.com'},
        {'email': 'zażółć@example.com'},
        {'email': 'a@[127.0.0.1]'},
        {'email': 'a..b@example.com'},
        {'code': 'abc'},
        {'code': 'ABC'},
        {'count': '12'},
        {'count': 12.0},
        {'count': 12.5},
        {'count': '12.000'},
        {'count': -1},
        {'count': 101},
        {'count': 13},
        {'count': True},
        {'count': ' 5'},
        {'count': '1e3'},
        {'count': 2**70},
        {'ratio': 1},
        {'ratio': 1.5},
        {'ratio': 2.0},
        {'ratio': '0.5'},
        {'flag': 'yes'},
        {'flag': 'off'},
        {'flag': 0},
        {'flag': 2},
        {'flag': 'maybe'},
        {'maybe': ''},
        {'maybe': 'null'},
        {'maybe': None},
        {'price': '1.5'},
        {'price': 1},
        {'price': '-0'},
        {'price': '999.99'},
        {'price': '1000'},
        {'price': '1.555'},
        {'price': '1e2'},
        {'price': 'NaN'},
        {'price': ''},
        {'price': 1.5},
        {'loose': '0001.2300'},
        {'day': '2024-02-29'},
        {'day': '2023-02-29'},
        {'day': '20240229'},
        {'day': '2024-02-29T10:00:00'},
        {'when': '2024-02-29T10:00:00Z'},
        {'when': '2024-02-29T10:00:00.123+05:30'},
        {'when': '2024-02-29T10:00:00'},
        {'when': '2024-02-29'},
        {'when': '2024-02-30T10:00:00Z'},
        {'when': 'garbage'},
        {'ident': '12345678-1234-5678-1234-567812345678'},
        {'ident': '12345678123456781234567812345678'},
        {'ident': '{12345678-1234-5678-1234-567812345678}'},
        {'ident': 'urn:uuid:12345678-1234-5678-1234-567812345678'},
        {'ident': '12345678-1234-5678-1234-56781234567x'},
        {'ident': 5},
        {'kind': 1},
        {'kind': '1'},
        {'kind': 'b'},
        {'kind': 'c'},
        {'kind': ''},
        {'tags': ['a', ' bc ']},
        {'tags': ['toolong']},
        {'tags': ['a', 'b', 'c', 'd']},
        {'tags': 'not-a-list'},
        {'tags': [None]},
        {'numbers': [1, None, '3']},
        {'numbers': [1, 'x']},
        {'nullable': None},
        {'default': None},
        {'renamed': 'deep'},
        {'child': {'id': 1}},
        {'child': {'id': 0}},
        {'child': 'x'},
        {'children': [{'id': 1}, {'id': 0}]},
        {'children': [{'id': 1}, {'id': 2}]},
        {'children': [{'id': 1}, None]},
        {'children': []},
        {'child': None},
        {'child': {'id': '5', 'extra': 1}},
        {'read_only': 'ignored', 'hidden': 'ignored', 'unknown': 1},
    ],
    ids=repr,
)
def test_matches_drf(payload):
    validate(InputSerializer, {**VALID, **payload})


def test_empty_payload():
    validate(InputSerializer, {})


def test_partial():
    validate(InputSerializer, {'count': '5'}, partial=True)


@pytest.mark.parametrize(
    'payload',
    [
        [{'name': 'Ala', 'count': 1}, {'name': 'Ola'}],
        [{'name': 'Ala', 'count': 1}, {'name': 'x'}, None, 'str', {'count': 13}],
        [],
        'not-a-list',
    ],
    ids=repr,
)
@pytest.mark.parametrize('kwargs', [{}, {'allow_empty': False}, {'max_length': 1}, {'min_length': 3}], ids=repr)
def test_many(payload, kwargs):
    validate(InputSerializer, payload, many=True, **kwargs)


def test_many_with_serializer_validate():
    validate(CrossFieldSerializer, [{'start': '2024-01-02', 'end': '2024-01-01'}], many=True)


def test_non_dict_input_uses_drf():
    validate(InputSerializer, ['not', 'a', 'dict'])


class CrossFieldSerializer(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()

    def validate(self, attrs):
        if attrs['end'] < attrs['start']:
            raise ValidationError({'end': 'before start'})
        return attrs


def test_validate_method():
    validate(CrossFieldSerializer, {'start': '2024-01-02', 'end': '2024-01-01'})
    ok, data = validate(CrossFieldSerializer, {'start': datetime.date(2024, 1, 1), 'end': '2024-01-02'})
    assert ok
