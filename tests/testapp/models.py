from django.db import models


class VersionField(models.Field):
    """A custom model field: DRF maps it to `ModelField`."""

    def get_internal_type(self):
        return 'IntegerField'


class Author(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)

    def get_display(self):
        return f'{self.name} <{self.email}>'


class Tag(models.Model):
    name = models.CharField(max_length=30, unique=True)


class Book(models.Model):
    class Kind(models.TextChoices):
        NOVEL = 'novel', 'Novel'
        POEM = 'poem', 'Poem'

    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.NOVEL)
    pages = models.PositiveIntegerField(default=0)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    rating = models.FloatField(null=True, blank=True)
    published = models.DateField(null=True)
    created = models.DateTimeField()
    available = models.BooleanField(default=True)
    author = models.ForeignKey(Author, related_name='books', on_delete=models.CASCADE)
    editor = models.ForeignKey(Author, related_name='edited', null=True, blank=True, on_delete=models.SET_NULL)
    tags = models.ManyToManyField(Tag, blank=True)
    meta = models.JSONField(default=dict)
    version = VersionField(default=1)
