import pytest

from fast_drf import serializers
from fast_drf._compiler import get_compiled
from tests.testapp.models import Author, Book, Tag
from tests.utils import compare, validate


class BookSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.name')
    author_display = serializers.CharField(source='author.get_display')
    editor_name = serializers.CharField(source='editor.name', default=None)

    class Meta:
        model = Book
        fields = '__all__'


class AuthorSerializer(serializers.ModelSerializer):
    books = BookSerializer(many=True, read_only=True)

    class Meta:
        model = Author
        fields = ['id', 'name', 'email', 'books']


class DeepBookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = '__all__'
        depth = 1


@pytest.mark.parametrize('serializer_class', [BookSerializer, DeepBookSerializer])
def test_books(books, serializer_class):
    compare(lambda: serializer_class(Book.objects.order_by('id'), many=True).data)


def test_nested_reverse_relation(books):
    compare(lambda: AuthorSerializer(Author.objects.order_by('id'), many=True).data)


def test_fk_uses_attname_without_query(books, django_assert_num_queries):
    book = Book.objects.get(pk=books[0].pk)
    read = get_compiled(BookSerializer(book)).describe()['read']
    assert read['author'] == ('pk_attname', 'pk')
    assert read['tags'] == ('python', 'pk_many')
    assert read['price'] == ('attrs', 'decimal')
    assert read['version'] == ('star', 'model_attr')

    class OnlyFk(serializers.ModelSerializer):
        class Meta:
            model = Book
            fields = ['author', 'editor']

    with django_assert_num_queries(0):
        assert OnlyFk(book).data == {'author': book.author_id, 'editor': book.editor_id}


def test_unsaved_instance(db):
    compare(lambda: BookSerializer(Book(title='new', price=1)).data)


WRITE = {
    'title': 'New',
    'kind': 'poem',
    'pages': 10,
    'price': '10.50',
    'created': '2024-01-01T10:00:00+01:00',
    'meta': {'a': 1},
}


class WritableBookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = ['title', 'kind', 'pages', 'price', 'rating', 'published', 'created', 'author', 'tags', 'meta']


@pytest.mark.parametrize(
    'payload',
    [
        {},
        {'title': 'x' * 201},
        {'kind': 'opera'},
        {'pages': -1},
        {'price': '123456.789'},
        {'author': 999},
        {'tags': [1, 999]},
        {'rating': None, 'published': None},
    ],
    ids=repr,
)
def test_model_validation(books, payload):
    author = books[0].author
    tags = list(Tag.objects.values_list('pk', flat=True))
    validate(WritableBookSerializer, {**WRITE, 'author': author.pk, 'tags': tags, **payload})


def test_unique_validator(books):
    class TagSerializer(serializers.ModelSerializer):
        class Meta:
            model = Tag
            fields = ['name']

    validate(TagSerializer, {'name': 'red'})
    validate(TagSerializer, {'name': 'green'})


def test_create(books):
    serializer = WritableBookSerializer(data={**WRITE, 'author': books[0].author.pk, 'tags': []})
    assert serializer.is_valid(), serializer.errors
    book = serializer.save()
    assert Book.objects.get(pk=book.pk).title == 'New'
