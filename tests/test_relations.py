from contextlib import contextmanager
from unittest import mock

import pytest
from django.db.models import Prefetch
from django.db.models.fields import related_descriptors

from drf_oxide import serializers
from drf_oxide._compiler import get_compiled
from tests.testapp.models import Author, AuthorProfile, Book, Tag
from tests.utils import compare


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name']


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuthorProfile
        fields = ['bio']


class AuthorSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(default=None)

    class Meta:
        model = Author
        fields = ['id', 'name', 'profile']


class BookSerializer(serializers.ModelSerializer):
    author = AuthorSerializer()
    editor = AuthorSerializer(allow_null=True)
    author_name = serializers.CharField(source='author.name')
    tags = TagSerializer(many=True)
    tag_ids = serializers.PrimaryKeyRelatedField(source='tags', many=True, read_only=True)

    class Meta:
        model = Book
        fields = ['id', 'title', 'author', 'editor', 'author_name', 'tags', 'tag_ids']


class AuthorWithBooksSerializer(serializers.ModelSerializer):
    books = BookSerializer(many=True)
    book_ids = serializers.PrimaryKeyRelatedField(source='books', many=True, read_only=True)

    class Meta:
        model = Author
        fields = ['id', 'books', 'book_ids']


@pytest.fixture
def library(books):
    AuthorProfile.objects.create(author=books[0].author, bio='poet')
    return books


def loaded_books():
    return list(Book.objects.select_related('author__profile', 'editor').prefetch_related('tags').order_by('id'))


@contextmanager
def count_descriptor_calls():
    calls = []
    classes = (
        related_descriptors.ForwardManyToOneDescriptor,
        related_descriptors.ReverseOneToOneDescriptor,
        related_descriptors.ReverseManyToOneDescriptor,
    )
    patches = []
    for cls in classes:
        original = cls.__get__

        def counting(self, instance, owner=None, _original=original):
            if instance is not None:
                calls.append(type(self).__name__)
            return _original(self, instance, owner)

        patches.append(mock.patch.object(cls, '__get__', counting))
    for patch in patches:
        patch.start()
    try:
        yield calls
    finally:
        for patch in patches:
            patch.stop()


def test_steps(library):
    read = get_compiled(BookSerializer(loaded_books()[0])).describe()['read']
    assert read['tag_ids'] == ('many', 'pk_many')
    assert read['tags'] == ('attrs', 'nested_many')


def test_cached_relations_skip_descriptors(library, django_assert_num_queries):
    rows = loaded_books()
    expected = compare(lambda: BookSerializer(rows, many=True).data)
    with django_assert_num_queries(0), count_descriptor_calls() as calls:
        assert BookSerializer(rows, many=True).data == expected
    # Only Bob (author of the 2nd book, editor of the 1st) has no profile: a cached `None` on a
    # reverse one-to-one makes Django raise, so the descriptor runs for those two.
    assert calls == ['ReverseOneToOneDescriptor', 'ReverseOneToOneDescriptor']


def test_reverse_many_prefetched(library, django_assert_num_queries):
    authors = list(
        Author.objects.prefetch_related(
            Prefetch('books', queryset=Book.objects.select_related('author__profile', 'editor').order_by('id')),
            'books__tags',
            'profile',
        ).order_by('id')
    )
    expected = compare(lambda: AuthorWithBooksSerializer(authors, many=True).data)
    with django_assert_num_queries(0):
        assert AuthorWithBooksSerializer(authors, many=True).data == expected


def test_not_cached_falls_back_to_queries(library):
    compare(lambda: BookSerializer(list(Book.objects.order_by('id')), many=True).data)
    compare(lambda: AuthorWithBooksSerializer(list(Author.objects.order_by('id')), many=True).data)


def test_cached_none(library):
    rows = loaded_books()
    assert rows[1].editor is None and not hasattr(rows[1].author, 'profile')
    compare(lambda: BookSerializer(rows, many=True).data)


def test_deleted_instance_raises_like_drf(library):
    author = Author.objects.prefetch_related('books').get(pk=library[1].author_id)
    Book.objects.filter(author=author).update(editor=None)
    author.books.all()  # noqa: B018 - make sure the prefetch cache is there
    tag = Tag.objects.create(name='orphan')
    tag.delete()  # pk becomes None

    for make in (
        lambda: AuthorWithBooksSerializer(author).data,
        lambda: TagSerializer(tag).data,
    ):
        import drf_oxide

        with drf_oxide.disabled():
            try:
                expected = make()
            except Exception as exc:  # noqa: BLE001
                expected = type(exc)
        try:
            actual = make()
        except Exception as exc:  # noqa: BLE001
            actual = type(exc)
        assert actual == expected


def test_pk_none_with_stale_prefetch_cache(library):
    author = Author.objects.prefetch_related('books').get(pk=library[0].author_id)
    author.pk = None

    import drf_oxide

    with drf_oxide.disabled(), pytest.raises(ValueError):
        AuthorWithBooksSerializer(author).data  # noqa: B018
    with pytest.raises(ValueError):
        AuthorWithBooksSerializer(author).data  # noqa: B018


class NonRelationManySourceSerializer(serializers.ModelSerializer):
    # `many=True` over something that is not a Django relation descriptor on the model.
    first_books = BookSerializer(source='get_first_books', many=True, read_only=True)

    class Meta:
        model = Author
        fields = ['id', 'first_books']


def test_many_source_that_is_not_a_relation(library):
    Author.get_first_books = lambda self: list(self.books.order_by('id')[:1])
    try:
        compare(lambda: NonRelationManySourceSerializer(list(Author.objects.order_by('id')), many=True).data)
    finally:
        del Author.get_first_books
