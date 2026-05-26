from django.urls import path

from .views import MyEarningsView

urlpatterns = [
    path('earnings/', MyEarningsView.as_view(), name='my-earnings'),
]
