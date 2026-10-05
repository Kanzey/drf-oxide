"""DRF vs drf_oxide. Run with `make bench`."""

import datetime
import decimal
import types
import uuid

import pytest
from rest_framework import renderers as drf_renderers
from rest_framework import serializers as drf

import drf_oxide
from drf_oxide import serializers
from drf_oxide.renderers import JSONRenderer

ITEMS = 1000


class ChildSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class RowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField()
    email = serializers.EmailField()
    count = serializers.IntegerField()
    ratio = serializers.FloatField()
    active = serializers.BooleanField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    day = serializers.DateField()
    moment = serializers.DateTimeField()
    ident = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=['a', 'b', 'c'])
    tags = serializers.ListField(child=serializers.CharField())
    owner = ChildSerializer()
    owner_name = serializers.CharField(source='owner.name')


def make_rows():
    moment = datetime.datetime(2024, 1, 1, 12, tzinfo=datetime.timezone.utc)
    return [
        types.SimpleNamespace(
            id=i,
            name=f'name {i}',
            description='lorem ipsum dolor sit amet ' * 3,
            email=f'user{i}@example.com',
            count=i * 3,
            ratio=i / 7,
            active=i % 2 == 0,
            price=decimal.Decimal(f'{i}.99'),
            day=datetime.date(2024, 1, 1 + i % 28),
            moment=moment,
            ident=uuid.UUID(int=i),
            kind='abc'[i % 3],
            tags=['x', 'y', 'z'],
            owner=types.SimpleNamespace(id=i, name=f'owner {i}'),
        )
        for i in range(ITEMS)
    ]


ROWS = make_rows()
PAYLOAD = [
    {
        'id': i,
        'name': f'name {i}',
        'description': 'lorem ipsum',
        'email': f'user{i}@example.com',
        'count': i,
        'ratio': 0.5,
        'active': True,
        'price': '12.50',
        'day': '2024-01-01',
        'moment': '2024-01-01T12:00:00Z',
        'ident': str(uuid.UUID(int=i)),
        'kind': 'a',
        'tags': ['x', 'y'],
        'owner': {'id': 1, 'name': 'owner'},
        'owner_name': 'owner',
    }
    for i in range(ITEMS)
]


def serialize():
    return RowSerializer(ROWS, many=True).data


def validate():
    serializer = RowSerializer(data=PAYLOAD, many=True)
    assert serializer.is_valid(), serializer.errors
    return serializer.validated_data


@pytest.mark.parametrize('impl', ['drf', 'fast'])
def test_serialize(benchmark, impl):
    if impl == 'drf':
        with drf_oxide.disabled():
            benchmark(serialize)
    else:
        benchmark(serialize)


@pytest.mark.parametrize('impl', ['drf', 'fast'])
def test_validate(benchmark, impl):
    if impl == 'drf':
        with drf_oxide.disabled():
            benchmark(validate)
    else:
        benchmark(validate)


@pytest.mark.parametrize('impl', ['drf', 'fast'])
def test_render(benchmark, impl):
    data = serialize()
    renderer = drf_renderers.JSONRenderer() if impl == 'drf' else JSONRenderer()
    benchmark(renderer.render, data)


assert drf.Serializer is not serializers.Serializer
