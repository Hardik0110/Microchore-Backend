from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/', include('projects.urls')),
    path('api/', include('submissions.urls')),
    path('api/', include('earnings.urls')),
    path('api/reviews/', include('reviews.urls')),
]
