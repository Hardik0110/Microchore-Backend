from django.urls import path

from .views import (
    ProjectDetailUpdateView,
    ProjectListCreateView,
    ProjectTaskCreateView,
    TaskDetailView,
    TaskListView,
)
from submissions.views import TaskClaimView

app_name = 'projects'

urlpatterns = [
    path('tasks/', TaskListView.as_view(), name='task-list'),
    path('tasks/<int:pk>/', TaskDetailView.as_view(), name='task-detail'),
    path('tasks/<int:pk>/claim/', TaskClaimView.as_view(), name='task-claim'),
    path('projects/', ProjectListCreateView.as_view(), name='project-list-create'),
    path('projects/<int:pk>/', ProjectDetailUpdateView.as_view(), name='project-detail'),
    path('projects/<int:pk>/tasks/', ProjectTaskCreateView.as_view(), name='project-task-create'),
]
