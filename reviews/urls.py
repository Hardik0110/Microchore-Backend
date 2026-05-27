from django.urls import path
from .views import ReviewCreateView, ReviewerQueueView, ReviewerStatsView

app_name = 'reviews'

urlpatterns = [
    path('queue/', ReviewerQueueView.as_view(), name='reviewer-queue'),
    path('me/stats/', ReviewerStatsView.as_view(), name='reviewer-stats'),
    path('submissions/<int:submission_id>/', ReviewCreateView.as_view(), name='review-create'),
]
