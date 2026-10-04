from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import AnonRateThrottle
from .serializers import (
    UserSerializer, RegisterSerializer, LoginSerializer,
    ChangePasswordSerializer, ForgotPasswordSerializer, ResetPasswordSerializer
)
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from .models import PasswordResetToken
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class LoginRateThrottle(AnonRateThrottle):
    scope = 'login'


class RegisterRateThrottle(AnonRateThrottle):
    scope = 'register'


class PasswordResetRateThrottle(AnonRateThrottle):
    scope = 'password_reset'


class UserExistsRateThrottle(AnonRateThrottle):
    scope = 'user_exists'


def send_password_reset_email(user, reset_token):
    reset_url = f"{settings.SITE_URL}/reset-password?token={reset_token}"
    subject = "Password Reset Request - LN Crawler"

    text_content = f"""
    Password Reset Request

    Hello {user.username},

    You have requested to reset your password. Copy and paste this URL into your browser to reset your password:

    {reset_url}

    This link will expire in 24 hours.

    If you didn't request this password reset, please ignore this email.

    Best regards,
    LN Crawler Team
    """

    html_content = f"""
    <html>
    <body>
        <h2>Password Reset Request</h2>
        <p>Hello {user.username},</p>
        <p>You have requested to reset your password. Click the link below to reset your password:</p>
        <p><a href="{reset_url}" style="background-color: #4CAF50; color: white; padding: 14px 25px; text-decoration: none; border-radius: 4px;">Reset Password</a></p>
        <p>If the button doesn't work, copy and paste this URL into your browser:</p>
        <p>{reset_url}</p>
        <p>This link will expire in 24 hours.</p>
        <p>If you didn't request this password reset, please ignore this email.</p>
        <br>
        <p>Best regards,<br>LN Crawler Team</p>
    </body>
    </html>
    """

    message = EmailMultiAlternatives(
        subject,
        text_content,
        f"{settings.EMAIL_SENDER_NAME} <{settings.DEFAULT_FROM_EMAIL}>",
        [user.email],
    )
    message.attach_alternative(html_content, "text/html")
    return message.send() > 0


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [RegisterRateThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            'token': token.key,
            'user': UserSerializer(user, context=self.get_serializer_context()).data
        }, status=status.HTTP_201_CREATED)

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data['username']
            password = serializer.validated_data['password']
            user = authenticate(username=username, password=password)
            
            if user:
                # Token-only API: no Django session is established, which avoids
                # login CSRF / session fixation.
                token, created = Token.objects.get_or_create(user=user)
                return Response({
                    'token': token.key,
                    'user': UserSerializer(user).data
                }, status=status.HTTP_200_OK)
            
            return Response({'error': 'Invalid Credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            request.user.auth_token.delete()
        except (AttributeError):
            pass
        
        return Response({"message": "Successfully logged out."}, status=status.HTTP_200_OK)

class UserProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

class UserExistsView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [UserExistsRateThrottle]

    def get(self, request):
        username = request.query_params.get('username', '')
        email = request.query_params.get('email', '')
        
        username_exists = User.objects.filter(username=username).exists() if username else False
        email_exists = User.objects.filter(email=email).exists() if email else False
        
        return Response({
            'username_exists': username_exists,
            'email_exists': email_exists
        })

class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            # Set new password
            request.user.set_password(serializer.validated_data['new_password'])
            request.user.save()
            
            # Invalidate all existing tokens for security
            Token.objects.filter(user=request.user).delete()
            
            # Create new token
            new_token = Token.objects.create(user=request.user)
            
            return Response({
                'message': 'Password changed successfully.',
                'token': new_token.key  # Return new token
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ForgotPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            user = User.objects.filter(email=email).first()

            if user:
                # Only one outstanding reset token per account: retire the
                # previous ones so an older (possibly leaked) link cannot be used.
                PasswordResetToken.objects.filter(user=user, used=False).update(used=True)
                reset_token = PasswordResetToken.objects.create(user=user)
                try:
                    send_password_reset_email(user, reset_token.token)
                except Exception as e:
                    logger.error(f"Error sending password reset email: {e}")

            # Always return the same response so the endpoint cannot be used to
            # discover which emails are registered.
            return Response({
                'message': 'If that email is registered, a password reset link has been sent.'
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            token = serializer.validated_data['token']
            new_password = serializer.validated_data['new_password']
            
            with transaction.atomic():
                reset_token = (
                    PasswordResetToken.objects
                    .select_for_update()
                    .filter(token=token)
                    .first()
                )
                
                if reset_token is None or not reset_token.is_valid():
                    return Response({
                        'error': 'Invalid or expired reset token.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                user = reset_token.user
                user.set_password(new_password)
                user.save()
                
                # Burn every outstanding reset token for this account.
                PasswordResetToken.objects.filter(user=user).update(used=True)
                
                # Invalidate all existing auth tokens for security
                Token.objects.filter(user=user).delete()
                
                return Response({
                    'message': 'Password reset successfully.'
                }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
