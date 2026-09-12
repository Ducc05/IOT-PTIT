from django.contrib.auth.models import AbstractUser

from libs.models.base_model import BaseModel


class User(AbstractUser, BaseModel):
    def __str__(self):
        return self.username
