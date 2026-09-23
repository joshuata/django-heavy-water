from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models


class Record(models.Model):
    """A row written by test builders, so tests can see which ones ran."""

    name = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.name


if TYPE_CHECKING:
    # BaseUserManager is only generic in django-stubs, not at run time.
    _EmailUserManagerBase = BaseUserManager["EmailUser"]
else:
    _EmailUserManagerBase = BaseUserManager


class EmailUserManager(_EmailUserManagerBase):
    def create_superuser(
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> "EmailUser":
        user = self.model(
            email=self.normalize_email(email),
            is_staff=True,
            is_superuser=True,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user


class EmailUser(AbstractBaseUser):
    """A custom user model that logs in by email and has no name fields."""

    email = models.EmailField(unique=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    objects = EmailUserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"

    def __str__(self) -> str:
        return self.email
