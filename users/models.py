from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user, swapped in from day one so it can grow later.

    Email is the login identifier (see ACCOUNT_LOGIN_METHODS), but Wagtail's
    admin still expects a username, so both are kept.
    """

    email = models.EmailField("email address", unique=True)
    display_name = models.CharField(max_length=120, blank=True)
    pronouns = models.CharField(max_length=60, blank=True)
    bio = models.TextField(blank=True)

    def __str__(self):
        return self.display_name or self.get_full_name() or self.email
