from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .serializers import UserSerializer, RegisterSerializer, LoginSerializer
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

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
