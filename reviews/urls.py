from django.urls import path
from .views import ReviewCreateView, ReviewerQueueView

app_name = 'reviews'

urlpatterns = [
    path('queue/', ReviewerQueueView.as_view(), name='reviewer-queue'),
    path('submissions/<int:submission_id>/', ReviewCreateView.as_view(), name='review-create'),
]
