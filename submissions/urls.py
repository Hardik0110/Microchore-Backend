from django.urls import path

from .views import MySubmissionListCreateView

urlpatterns = [
    path('submissions/', MySubmissionListCreateView.as_view(), name='my-submissions'),
]
