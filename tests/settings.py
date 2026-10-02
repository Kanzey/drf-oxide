SECRET_KEY = 'fast-drf-tests'
USE_TZ = True
TIME_ZONE = 'Europe/Warsaw'
INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'rest_framework',
    'tests.testapp',
]
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
ROOT_URLCONF = 'tests.testapp.urls'
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': ['fast_drf.renderers.JSONRenderer'],
    'DEFAULT_PARSER_CLASSES': ['fast_drf.parsers.JSONParser'],
    'UNAUTHENTICATED_USER': None,
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'DEFAULT_PERMISSION_CLASSES': [],
}
