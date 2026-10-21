from django.contrib.auth.models import AbstractUser
from django.db import models

from libs.models.base_model import BaseModel


class User(AbstractUser, BaseModel):
    full_name = models.CharField(max_length=150, blank=True)
    student_id = models.CharField(max_length=32, null=True, blank=True, unique=True)
    avatar = models.ImageField(upload_to="avatars/%Y/%m/", blank=True)

    def __str__(self):
        return self.username
