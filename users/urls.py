from django.urls import path
from users.views import (
    RegisterView,
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    LogoutView,
    UserProfileView,
    ChangePasswordView,
)

app_name = 'users'

urlpatterns = [
    # Registration & Verification
    path('register/', RegisterView.as_view(), name='register'),
    
    # JWT Session control
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    
    # Profiles & Passwords
    path('me/', UserProfileView.as_view(), name='me'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
]
