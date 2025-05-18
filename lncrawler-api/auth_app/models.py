from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    profile_pic = models.ImageField(upload_to='profile_pics/', blank=True, null=True)

    def __str__(self):
        return self.username