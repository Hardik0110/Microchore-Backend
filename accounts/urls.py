from django.urls import path

from .admin_views import AdminPromoteReviewerView, AdminUserListView
from .views import (
    EmailTokenObtainPairView,
    EmailVerifyConfirmView,
    EmailVerifyRequestView,
    GoogleSignInView,
    LinkYouTubeView,
    LogoutView,
    MeView,
    NotificationListView,
    NotificationMarkAllReadView,
    NotificationMarkReadView,
    SignupView,
    ThrottledTokenRefreshView,
    TwitterCallbackView,
    TwitterStartView,
)

app_name = 'accounts'

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('google/', GoogleSignInView.as_view(), name='google_signin'),
    path('token/', EmailTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', ThrottledTokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', MeView.as_view(), name='me'),
    path('email/verify/request/', EmailVerifyRequestView.as_view(), name='email_verify_request'),
    path('email/verify/confirm/', EmailVerifyConfirmView.as_view(), name='email_verify_confirm'),
    path('social/youtube/', LinkYouTubeView.as_view(), name='link_youtube'),
    path('social/twitter/start/', TwitterStartView.as_view(), name='twitter_start'),
    path('twitter/callback', TwitterCallbackView.as_view(), name='twitter_callback'),
    path('notifications/', NotificationListView.as_view(), name='notification_list'),
    path('notifications/<int:pk>/read/', NotificationMarkReadView.as_view(), name='notification_mark_read'),
    path('notifications/read-all/', NotificationMarkAllReadView.as_view(), name='notification_mark_all_read'),
    path('admin/users/', AdminUserListView.as_view(), name='admin_user_list'),
    path('admin/users/<int:pk>/promote-reviewer/', AdminPromoteReviewerView.as_view(), name='admin_promote_reviewer'),
]
