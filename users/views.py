from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, OpenApiResponse
from users.serializers import (
    UserRegisterSerializer,
    UserSerializer,
    ChangePasswordSerializer,
)

User = get_user_model()

class RegisterView(generics.CreateAPIView):
    """
    Register a new user in the system.
    """
    queryset = User.objects.all()
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Register a new user",
        responses={
            201: UserSerializer,
            400: OpenApiResponse(description="Validation error (e.g. email already exists or weak password)")
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        # Return serialized user detail
        user_serializer = UserSerializer(user)
        return Response(user_serializer.data, status=status.HTTP_201_CREATED)


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Obtain JWT access and refresh token pair using email and password.
    """
    @extend_schema(
        summary="User Login (Obtain JWT)",
        description="Authenticates credentials and returns access & refresh tokens."
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class CustomTokenRefreshView(TokenRefreshView):
    """
    Obtain a fresh JWT access token using a valid refresh token.
    """
    @extend_schema(
        summary="Refresh JWT Access Token",
        description="Provides a new access token when the current one expires."
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class LogoutView(APIView):
    """
    Blacklist the provided refresh token to end the session.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="User Logout",
        description="Invalidates the refresh token so it cannot be used again.",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "refresh": {"type": "string", "description": "The refresh token to blacklist"}
                },
                "required": ["refresh"]
            }
        },
        responses={
            205: OpenApiResponse(description="Token blacklisted successfully"),
            400: OpenApiResponse(description="Invalid token or missing parameter")
        }
    )
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response(
                    {"detail": "Refresh token is required in the body under 'refresh'."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    Retrieve or update the authenticated user's profile and notification settings.
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # Always return the current authenticated user
        return self.request.user

    @extend_schema(
        summary="Retrieve user profile",
        responses={200: UserSerializer}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Update user profile",
        responses={200: UserSerializer}
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @extend_schema(
        summary="Partial update user profile",
        responses={200: UserSerializer}
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)


class ChangePasswordView(generics.GenericAPIView):
    """
    Update the authenticated user's password.
    """
    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Change user password",
        responses={
            200: OpenApiResponse(description="Password changed successfully"),
            400: OpenApiResponse(description="Validation error (e.g. incorrect old password or weak new password)")
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Password has been changed successfully."},
            status=status.HTTP_200_OK
        )
