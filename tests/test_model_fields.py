import datetime

import pytest
from django.test import override_settings
from django.utils import translation

import fast_drf
from fast_drf import _model_fields, serializers
from tests.testapp.models import Author, Book, Membership


class BookSerializer(serializers.ModelSerializer):
    title_upper = serializers.CharField(source='title', read_only=True)

    class Meta:
        model = Book
        fields = '__all__'
        read_only_fields = ['created']
        extra_kwargs = {'pages': {'min_value': 10}, 'title': {'label': 'Tytuł'}}


class DeepBookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        exclude = ['meta']
        depth = 2


class MembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = ['author', 'role']


class CustomBuildSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = '__all__'

    def build_field(self, *args):
        return super().build_field(*args)


@pytest.mark.parametrize('serializer_class', [BookSerializer, DeepBookSerializer, MembershipSerializer])
def test_same_fields_as_drf(serializer_class):
    with fast_drf.disabled():
        expected = repr(serializer_class())
    assert repr(serializer_class()) == expected  # builds the recipe
    assert repr(serializer_class()) == expected  # replays it
    assert serializer_class in {key[0] for key in _model_fields._recipes}


def test_hidden_unique_together_field():
    for _ in range(2):
        fields = MembershipSerializer().fields
        assert type(fields['joined']).__name__ == 'HiddenField'
        assert fields['joined'].default == datetime.date(2024, 1, 1)


def test_fields_are_not_shared():
    first, second = DeepBookSerializer(), DeepBookSerializer()
    for name in first.fields:
        assert first.fields[name] is not second.fields[name]
        assert first.fields[name].parent is first
    assert first.fields['tags'].child is not second.fields['tags'].child
    books = BookSerializer(), BookSerializer()
    assert books[0].fields['tags'].child_relation is not books[1].fields['tags'].child_relation


def test_custom_build_methods_are_not_cached():
    with fast_drf.disabled():
        expected = repr(CustomBuildSerializer())
    assert repr(CustomBuildSerializer()) == expected
    assert CustomBuildSerializer not in {key[0] for key in _model_fields._recipes}


def test_recipe_per_language_and_settings():
    with translation.override('pl'):
        MembershipSerializer().fields  # noqa: B018
    with translation.override('en'):
        MembershipSerializer().fields  # noqa: B018
    languages = {key[1] for key in _model_fields._recipes if key[0] is MembershipSerializer}
    assert {'pl', 'en'} <= languages

    with override_settings(REST_FRAMEWORK={'COERCE_DECIMAL_TO_STRING': False}):
        assert not _model_fields._recipes
        with fast_drf.disabled():
            expected = repr(BookSerializer())
        assert repr(BookSerializer()) == expected


@pytest.mark.django_db
def test_data_and_validation(books):
    from tests.utils import compare, validate

    compare(lambda: BookSerializer(Book.objects.order_by('id'), many=True).data)
    author = Author.objects.first()
    validate(MembershipSerializer, {'author': author.pk, 'role': 'a'})
    validate(MembershipSerializer, {'author': author.pk, 'role': 'x'})


@pytest.mark.parametrize('serializer_class', [BookSerializer, DeepBookSerializer, MembershipSerializer])
def test_prototype_copies_equal_fresh_fields(serializer_class):
    serializer_class().fields  # noqa: B018 - builds the recipe
    recipe = next(r for key, r in _model_fields._recipes.items() if key[0] is serializer_class)
    copied = 0
    for _, spec in recipe:
        if spec is None or spec[2] is None:
            continue
        field_class, field_kwargs, prototype = spec
        copy = _model_fields.instantiate(field_class, field_kwargs, prototype)
        expected = field_class(**field_kwargs)
        actual, wanted = dict(vars(copy)), dict(vars(expected))
        actual.pop('_creation_counter'), wanted.pop('_creation_counter')
        # Validators created in __init__ are stateless and shared by the copies.
        validators = actual.pop('_validators', None), wanted.pop('_validators', None)
        assert actual == wanted
        assert [describe(v) for v in validators[0] or []] == [describe(v) for v in validators[1] or []]
        for key, value in actual.items():
            if isinstance(value, (list, dict, set)):
                assert value is not vars(prototype)[key], key
        copied += 1
    assert copied


def describe(validator):
    return type(validator), getattr(validator, 'limit_value', None)


def test_changing_one_instance_does_not_leak():
    first, second = BookSerializer(), BookSerializer()
    first.fields['title'].validators.append(lambda value: None)
    first.fields['kind'].error_messages['invalid_choice'] = 'changed'
    assert len(second.fields['title'].validators) == len(BookSerializer().fields['title'].validators)
    assert second.fields['kind'].error_messages['invalid_choice'] != 'changed'


class NestedBookSerializer(serializers.ModelSerializer):
    memberships = MembershipSerializer(source='membership_set', many=True, read_only=True)

    class Meta:
        model = Author
        fields = ['id', 'memberships']


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_language_is_fixed_for_the_whole_compilation(language):
    from fast_drf._compiler import get_compiled
    from fast_drf._model_fields import compile_language

    _model_fields._recipes.clear()
    with translation.override(language):
        assert get_compiled(NestedBookSerializer()) is not None
    assert {key[1] for key in _model_fields._recipes} == {language}
    assert compile_language.get() is None
