from django.apps import AppConfig

from .patch import patch


class DrfOxideConfig(AppConfig):
    """Put `'drf_oxide'` first in `INSTALLED_APPS` to swap DRF's classes before any app imports its serializers."""

    name = 'drf_oxide'
    verbose_name = 'drf-oxide'

    def __init__(self, app_name, app_module):
        # Django registers apps one by one, importing each just before; `ready()` would be too late.
        patch()
        super().__init__(app_name, app_module)
