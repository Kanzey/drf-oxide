from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from fast_drf import serializers

from .models import Book


class BookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = ['id', 'title', 'price', 'author', 'tags', 'created']


@api_view(['GET', 'POST'])
def books(request):
    if request.method == 'POST':
        serializer = BookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(BookSerializer(serializer.save()).data, status=201)
    return Response(BookSerializer(Book.objects.order_by('id'), many=True).data)


urlpatterns = [path('books/', books)]
