import datetime
import decimal

import pytest

from drf_oxide import _state
from tests.testapp.models import Author, Book, Tag

_state.strict = True


@pytest.fixture
def books(db):
    alice = Author.objects.create(name='Alice', email='alice@example.com')
    bob = Author.objects.create(name='Bob')
    red, blue = Tag.objects.create(name='red'), Tag.objects.create(name='blue')
    created = datetime.datetime(2024, 3, 31, 1, 30, tzinfo=datetime.timezone.utc)
    first = Book.objects.create(
        title='Pan Tadeusz',
        kind=Book.Kind.POEM,
        pages=350,
        price=decimal.Decimal('39.90'),
        rating=4.5,
        published=datetime.date(1834, 6, 28),
        created=created,
        author=alice,
        editor=bob,
        meta={'isbn': '978-83', 'langs': ['pl', 'en']},
    )
    first.tags.set([red, blue])
    second = Book.objects.create(
        title='Lalka', price=decimal.Decimal('25'), created=created, author=bob, available=False
    )
    return [first, Book.objects.get(pk=second.pk)]
