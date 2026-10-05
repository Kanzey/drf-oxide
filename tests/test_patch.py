import subprocess
import sys
import textwrap


def test_patch_swaps_classes():
    code = textwrap.dedent(
        """
        import django
        from django.conf import settings
        settings.configure(INSTALLED_APPS=['rest_framework'])
        django.setup()

        import drf_oxide
        drf_oxide.patch()

        from rest_framework import parsers, renderers, serializers
        from drf_oxide import serializers as fast

        class S(serializers.Serializer):
            a = serializers.IntegerField()

        assert issubclass(S, fast.FastSerializerMixin)

        class M(serializers.ModelSerializer):
            pass

        # DRF's hierarchy holds for the swapped classes.
        assert issubclass(M, serializers.Serializer) and issubclass(M, serializers.BaseSerializer)
        assert issubclass(serializers.HyperlinkedModelSerializer, serializers.ModelSerializer)
        assert issubclass(serializers.ListSerializer, serializers.BaseSerializer)
        assert type(S([], many=True)) is fast.ListSerializer
        assert renderers.JSONRenderer.__module__ == 'drf_oxide.renderers'
        assert parsers.JSONParser.__module__ == 'drf_oxide.parsers'
        print(dict(S({'a': 1}).data))
        """
    )
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "{'a': 1}"


def run(code):
    return subprocess.run([sys.executable, '-c', textwrap.dedent(code)], capture_output=True, text=True, check=True)


def test_app_config_patches_before_other_apps():
    result = run(
        """
        import django
        from django.conf import settings
        settings.configure(INSTALLED_APPS=['drf_oxide', 'rest_framework', 'django.contrib.contenttypes'])
        django.setup()

        from rest_framework import serializers
        from drf_oxide.serializers import FastSerializerMixin
        assert issubclass(serializers.ModelSerializer, FastSerializerMixin)
        print('ok')
        """
    )
    assert result.stdout.strip() == 'ok'


def test_warns_about_serializers_defined_too_early():
    result = run(
        """
        import warnings
        import django
        from django.conf import settings
        settings.configure(INSTALLED_APPS=['rest_framework'])
        django.setup()

        from rest_framework import serializers

        class Early(serializers.Serializer):
            pass

        import drf_oxide
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            drf_oxide.patch()
        print(caught[0].message)
        """
    )
    assert '__main__.Early' in result.stdout
