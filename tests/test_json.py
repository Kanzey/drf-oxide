import datetime
import decimal
import io
import uuid

import pytest
from django.utils.translation import gettext_lazy
from rest_framework import parsers as drf_parsers
from rest_framework import renderers as drf_renderers
from rest_framework.exceptions import ParseError

from fast_drf.parsers import JSONParser
from fast_drf.renderers import JSONRenderer


class Strange:
    def __iter__(self):
        return iter([1, 2])


DATA = [
    None,
    {'a': 1, 'b': [1.5, None, True], 'c': {'d': 'zażółć   "q"'}},
    [decimal.Decimal('1.10'), uuid.UUID(int=5), datetime.date(2024, 1, 2)],
    {'dt': datetime.datetime(2024, 1, 2, 3, 4, tzinfo=datetime.timezone.utc), 't': datetime.time(1, 2)},
    {'delta': datetime.timedelta(seconds=90), 'lazy': gettext_lazy('lazy'), 'bytes': b'raw'},
    {'gen': Strange(), 'set': {1}},
    {1: 'int key', None: 'none'},
]


@pytest.mark.parametrize('data', DATA, ids=repr)
@pytest.mark.parametrize('media_type', [None, 'application/json; indent=2'])
def test_renderer_matches_drf(data, media_type):
    expected = drf_renderers.JSONRenderer().render(data, media_type)
    assert JSONRenderer().render(data, media_type) == expected


def test_renderer_options():
    class Loose(JSONRenderer):
        ensure_ascii = False
        compact = False
        strict = False

    class LooseDRF(drf_renderers.JSONRenderer):
        ensure_ascii = False
        compact = False
        strict = False

    data = {'x': float('nan'), 'y': 'ąę '}
    assert Loose().render(data) == LooseDRF().render(data)


@pytest.mark.parametrize(
    'body',
    [b'{"a": [1, 2.5, "x", null]}', b'[]', b'  "\\u017c"  ', b'1e400', '{"ż": 1}'.encode()],
)
def test_parser_matches_drf(body):
    assert JSONParser().parse(io.BytesIO(body)) == drf_parsers.JSONParser().parse(io.BytesIO(body))


@pytest.mark.parametrize('body', [b'{"a": }', b'[NaN]', b'\xef\xbb\xbf{}', b''])
def test_parser_errors_match_drf(body):
    with pytest.raises(ParseError) as expected:
        drf_parsers.JSONParser().parse(io.BytesIO(body))
    with pytest.raises(ParseError) as actual:
        JSONParser().parse(io.BytesIO(body))
    assert str(actual.value) == str(expected.value)


def test_api_view(client, books):
    response = client.get('/books/')
    assert response.status_code == 200
    assert [book['title'] for book in response.json()] == ['Pan Tadeusz', 'Lalka']

    payload = {'title': 'x', 'price': '1.00', 'author': books[0].author_id, 'tags': [], 'created': '2024-01-01T10:00'}
    response = client.post('/books/', data=payload, content_type='application/json')
    assert response.status_code == 201
    assert response.json()['created'] == '2024-01-01T10:00:00+01:00'

    response = client.post('/books/', data={**payload, 'price': '1.001'}, content_type='application/json')
    assert response.status_code == 400
    assert response.json() == {'price': ['Ensure that there are no more than 2 decimal places.']}
