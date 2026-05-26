from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    EmailTokenObtainPairView,
    GoogleSignInView,
    LinkYouTubeView,
    MeView,
    SignupView,
    TwitterCallbackView,
    TwitterStartView,
)

app_name = 'accounts'

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('google/', GoogleSignInView.as_view(), name='google_signin'),
    path('token/', EmailTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', MeView.as_view(), name='me'),
    path('social/youtube/', LinkYouTubeView.as_view(), name='link_youtube'),
    path('social/twitter/start/', TwitterStartView.as_view(), name='twitter_start'),
    path('twitter/callback', TwitterCallbackView.as_view(), name='twitter_callback'),
]
