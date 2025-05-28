from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .serializers import (
    UserSerializer, RegisterSerializer, LoginSerializer,
    ChangePasswordSerializer, ForgotPasswordSerializer, ResetPasswordSerializer
)
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from .models import PasswordResetToken
from .email_service import email_service
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

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

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data['username']
            password = serializer.validated_data['password']
            user = authenticate(username=username, password=password)
            
            if user:
                login(request, user)
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
        
        logout(request)
        return Response({"message": "Successfully logged out."}, status=status.HTTP_200_OK)

class UserProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

class UserExistsView(APIView):
    permission_classes = [permissions.AllowAny]

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

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            user = User.objects.get(email=email)
            
            # Create password reset token
            reset_token = PasswordResetToken.objects.create(user=user)
            
            # Send email
            email_sent = email_service.send_password_reset_email(
                user_email=user.email,
                username=user.username,
                reset_token=reset_token.token
            )
            
            if email_sent:
                return Response({
                    'message': 'Password reset email sent successfully.'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'error': 'Failed to send email. Please try again later.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            token = serializer.validated_data['token']
            new_password = serializer.validated_data['new_password']
            
            try:
                reset_token = PasswordResetToken.objects.get(token=token)
                
                if not reset_token.is_valid():
                    return Response({
                        'error': 'Invalid or expired reset token.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Reset password
                user = reset_token.user
                user.set_password(new_password)
                user.save()
                
                # Mark token as used
                reset_token.used = True
                reset_token.save()
                
                # Invalidate all existing tokens for security
                Token.objects.filter(user=user).delete()
                
                return Response({
                    'message': 'Password reset successfully.'
                }, status=status.HTTP_200_OK)
                
            except PasswordResetToken.DoesNotExist:
                return Response({
                    'error': 'Invalid reset token.'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
