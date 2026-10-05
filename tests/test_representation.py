import datetime
import decimal
import types
import uuid
import zoneinfo

import pytest
from django.utils import timezone

from drf_oxide import serializers
from drf_oxide._compiler import get_compiled
from tests.utils import compare


class Thing(types.SimpleNamespace):
    def get_label(self):
        return f'label:{self.name}'


class ChildSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class KitchenSinkSerializer(serializers.Serializer):
    name = serializers.CharField()
    email = serializers.EmailField()
    count = serializers.IntegerField()
    ratio = serializers.FloatField()
    active = serializers.BooleanField()
    price = serializers.DecimalField(max_digits=6, decimal_places=2)
    price_number = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False)
    day = serializers.DateField()
    moment = serializers.DateTimeField()
    moment_utc = serializers.DateTimeField(source='moment', default_timezone=datetime.timezone.utc)
    clock = serializers.TimeField()
    ident = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=[(1, 'one'), (2, 'two'), ('x', 'ex')])
    tags = serializers.ListField(child=serializers.CharField())
    scores = serializers.DictField(child=serializers.IntegerField())
    payload = serializers.JSONField()
    raw = serializers.ReadOnlyField(source='name')
    label = serializers.CharField(source='get_label')
    nested_name = serializers.CharField(source='child.name', default=None)
    child = ChildSerializer()
    children = ChildSerializer(many=True)
    method = serializers.SerializerMethodField()
    optional = serializers.CharField(required=False)
    nullable = serializers.CharField(allow_null=True)

    def get_method(self, obj):
        return [obj.count, self.context.get('extra')]


def make_thing(**overrides):
    values = dict(
        name='Zażółć',
        email='a@b.pl',
        count=3,
        ratio=0.5,
        active=True,
        price=decimal.Decimal('12.30'),
        price_number=decimal.Decimal('1.5'),
        day=datetime.date(2024, 2, 29),
        moment=datetime.datetime(2024, 3, 31, 1, 30, 15, 123, tzinfo=datetime.timezone.utc),
        clock=datetime.time(12, 30, 1, 5),
        ident=uuid.UUID('12345678-1234-5678-1234-567812345678'),
        kind=1,
        tags=['a', 'b', None],
        scores={'x': 1, 2: None},
        payload={'any': ['json', 1]},
        child=Thing(id=1, name='first'),
        children=[Thing(id=2, name='second'), Thing(id=3, name='third')],
    )
    values.update(overrides)
    return Thing(**values)


def test_kitchen_sink_is_fully_native():
    read = get_compiled(KitchenSinkSerializer(make_thing())).describe()['read']
    assert read == {
        'name': ('attrs', 'str'),
        'email': ('attrs', 'str'),
        'count': ('attrs', 'int'),
        'ratio': ('attrs', 'float'),
        'active': ('attrs', 'bool'),
        'price': ('attrs', 'decimal'),
        'price_number': ('attrs', 'decimal'),
        'day': ('attrs', 'date'),
        'moment': ('attrs', 'datetime'),
        'moment_utc': ('attrs', 'datetime'),
        'clock': ('attrs', 'time'),
        'ident': ('attrs', 'uuid'),
        'kind': ('attrs', 'choice'),
        'tags': ('attrs', 'list[str]'),
        'scores': ('attrs', 'dict[int]'),
        'payload': ('attrs', 'passthrough'),
        'raw': ('attrs', 'passthrough'),
        'label': ('attrs', 'str'),
        'nested_name': ('attrs', 'str'),
        'child': ('attrs', 'nested'),
        'children': ('attrs', 'nested_many'),
        'method': ('star', 'method'),
        'optional': ('attrs', 'str'),
        'nullable': ('attrs', 'str'),
    }


def test_kitchen_sink():
    compare(lambda: KitchenSinkSerializer(make_thing(), context={'extra': 'ctx'}).data)


def test_many():
    things = [make_thing(count=i, name=f'n{i}') for i in range(5)]
    compare(lambda: KitchenSinkSerializer(things, many=True).data)


@pytest.mark.parametrize(
    'overrides',
    [
        {'name': 123, 'count': '7', 'ratio': 2, 'active': 1, 'kind': 'x'},
        {'active': 'yes', 'kind': 3, 'kind_extra': None},
        {'price': decimal.Decimal('1.239'), 'price_number': 2},
        {'price': decimal.Decimal('1E+2'), 'price_number': decimal.Decimal('-0.005')},
        {'price': 5.5},
        {'moment': datetime.datetime(2024, 1, 1, 12, 0), 'day': '2024-01-01'},
        {'moment': datetime.datetime(2024, 1, 1, 12, 0, tzinfo=zoneinfo.ZoneInfo('America/New_York'))},
        {'child': None, 'children': [], 'nullable': None},
        {'tags': ('tuple', 'works'), 'scores': {}},
        {'ident': '12345678-1234-5678-1234-567812345678'},
    ],
)
def test_edge_values(overrides):
    compare(lambda: KitchenSinkSerializer(make_thing(**overrides)).data)


def test_active_timezone_is_respected():
    with timezone.override(zoneinfo.ZoneInfo('Asia/Tokyo')):
        data = compare(lambda: KitchenSinkSerializer(make_thing()).data)
    assert data['moment'].endswith('+09:00')
    assert data['moment_utc'].endswith('Z')


def test_dict_instance():
    compare(lambda: ChildSerializer({'id': 1, 'name': 'from dict'}).data)


def test_missing_attribute_raises_like_drf():
    with pytest.raises(AttributeError) as fast_exc:
        ChildSerializer(Thing(id=1)).data  # noqa: B018
    assert 'Got AttributeError when attempting to get a value for field `name`' in str(fast_exc.value)


class OverridingSerializer(serializers.Serializer):
    value = serializers.IntegerField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['extra'] = True
        return data


class CustomField(serializers.CharField):
    def to_representation(self, value):
        return value.upper()


class WithCustomFieldSerializer(serializers.Serializer):
    name = CustomField()
    items = OverridingSerializer(many=True)


def test_overrides_are_respected():
    thing = Thing(name='abc', items=[Thing(value=1), Thing(value=2)])
    data = compare(lambda: WithCustomFieldSerializer(thing).data)
    assert data['name'] == 'ABC'
    assert data['items'][0]['extra'] is True


class OptOutSerializer(serializers.Serializer):
    drf_oxide = False
    value = serializers.IntegerField()


def test_opt_out():
    serializer = OptOutSerializer(Thing(value=1))
    assert serializer.data == {'value': 1}
    assert get_compiled(serializer) is None


def test_dynamic_fields_per_instance():
    class DynamicSerializer(serializers.Serializer):
        a = serializers.IntegerField()
        b = serializers.IntegerField()

        def __init__(self, *args, only=None, **kwargs):
            super().__init__(*args, **kwargs)
            if only:
                for name in set(self.fields) - set(only):
                    self.fields.pop(name)

    thing = Thing(a=1, b=2)
    assert DynamicSerializer(thing, only=['a']).data == {'a': 1}
    assert DynamicSerializer(thing).data == {'a': 1, 'b': 2}
