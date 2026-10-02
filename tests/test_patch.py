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

        import fast_drf
        fast_drf.patch()

        from rest_framework import parsers, renderers, serializers
        from fast_drf import serializers as fast

        class S(serializers.Serializer):
            a = serializers.IntegerField()

        assert issubclass(S, fast.FastSerializerMixin)
        assert type(S([], many=True)) is fast.ListSerializer
        assert renderers.JSONRenderer.__module__ == 'fast_drf.renderers'
        assert parsers.JSONParser.__module__ == 'fast_drf.parsers'
        print(dict(S({'a': 1}).data))
        """
    )
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "{'a': 1}"
