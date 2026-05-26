from django.urls import path

from .views import TaskDetailView, TaskListView
from submissions.views import TaskClaimView

app_name = 'projects'

urlpatterns = [
    path('tasks/', TaskListView.as_view(), name='task-list'),
    path('tasks/<int:pk>/', TaskDetailView.as_view(), name='task-detail'),
    path('tasks/<int:pk>/claim/', TaskClaimView.as_view(), name='task-claim'),
]
