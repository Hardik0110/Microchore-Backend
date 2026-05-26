from django.urls import path

from .views import MySubmissionListCreateView, SubmissionReviewView

urlpatterns = [
    path('submissions/', MySubmissionListCreateView.as_view(), name='my-submissions'),
    path('submissions/<int:pk>/review/', SubmissionReviewView.as_view(), name='submission-review'),
]
