from django.db import models
from django.utils import timezone

class AuthToken(models.Model):
    access_token = models.TextField()
    updated_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Token last updated at {self.updated_at}"
