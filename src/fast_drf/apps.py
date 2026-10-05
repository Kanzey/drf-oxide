from django.apps import AppConfig

from .patch import patch


class FastDrfConfig(AppConfig):
    """Put `'fast_drf'` first in `INSTALLED_APPS` to swap DRF's classes before any app imports its serializers."""

    name = 'fast_drf'
    verbose_name = 'fast-drf'

    def __init__(self, app_name, app_module):
        # Django registers apps one by one, importing each just before; `ready()` would be too late.
        patch()
        super().__init__(app_name, app_module)
