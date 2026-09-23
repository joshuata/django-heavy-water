"""Base class for data builders run by the ``heavy_water`` management command."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, cast

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AbstractUser, UserManager

from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist
from django.core.management.base import OutputWrapper
from django.core.management.color import Style
from django.db import transaction
from django.db.models import Model

from heavy_water.conf import app_settings


def _has_field(model: type[Model], name: str) -> bool:
    """Return whether ``model`` has a field called ``name``."""
    try:
        model._meta.get_field(name)
    except FieldDoesNotExist:
        return False
    return True


class BaseDataBuilder(ABC):
    """Base class for a unit of seed data.

    Subclass it in an app's ``fixtures`` module (see ``HEAVY_WATER_FIXTURE_MODULE``)
    and implement :meth:`handle`. The ``heavy_water`` command discovers every
    subclass, and runs each one whose :meth:`should_run` returns ``True``.

    Attributes:
        app_name: Name of the app the builder was discovered in.
        stdout: The command's output stream, for progress messages.
        stderr: The command's error stream.
        style: The command's style, for coloring output (``self.style.SUCCESS``).
        database: Alias of the database to seed: the command's ``--database``, or
            ``HEAVY_WATER_DATABASE``.
            The builder's savepoint and :meth:`get_or_create_superuser` use it;
            queries in :meth:`handle` should too, via ``.using(self.database)``.
        depends_on: Builder classes that must run before this one. If one of
            them fails, this builder doesn't run and is reported as failed; if
            one is skipped, this builder is skipped too. Each must be a builder
            the command discovers.
    """

    depends_on: ClassVar[Sequence[type[BaseDataBuilder]]] = ()

    def __init__(
        self,
        app_name: str,
        stdout: OutputWrapper,
        stderr: OutputWrapper,
        style: Style,
        database: str | None = None,
    ) -> None:
        self.app_name = app_name
        self.stdout = stdout
        self.stderr = stderr
        self.style = style
        self.database = database or app_settings.DATABASE

    @property
    def builder_name(self) -> str:
        return f"{self.app_name} - {self.__class__.__name__}"

    def _heavy_water(self, *args: Any, **options: Any) -> bool:
        """Run :meth:`handle` in a savepoint, if :meth:`should_run` allows it.

        ``args`` and ``options`` are the command's arguments, passed through to
        :meth:`should_run`.

        Any exception rolls back this builder's changes and propagates to the
        caller. An ``AssertionError`` is also reported to stderr first.

        Returns:
            ``True`` if the builder ran, ``False`` if it was skipped.
        """
        if not self.should_run(*args, **options):
            self.stdout.write(f"{self.builder_name}: Skipped")
            return False
        try:
            with transaction.atomic(using=self.database):
                self.handle()
        except AssertionError:
            self.stderr.write(
                self.style.ERROR(
                    f"{self.builder_name}: Assertion failed setting up data"
                )
            )
            self.stderr.write(self.style.ERROR("Rolling back transaction"))
            raise
        self.stdout.write(
            self.style.SUCCESS(f"{self.builder_name}: Successfully set up data")
        )
        return True

    def get_or_create_superuser(
        self,
        username: str | None = None,
        email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        password: str | None = None,
        configure_user: Callable[[AbstractBaseUser], None] | None = None,
    ) -> AbstractBaseUser:
        """Return the superuser identified by ``username``, creating it if needed.

        ``username`` is the value of the user model's ``USERNAME_FIELD``. When
        that field is the email field and ``username`` is omitted, ``email`` is
        used as the identifier. Name fields are only set on models that have them.

        Omitted arguments fall back to the ``HEAVY_WATER_SUPERUSER_*`` settings.
        ``email``, ``first_name``, ``last_name`` and ``password`` are only used
        when the user is created; an existing user is returned unchanged.

        Args:
            username: Value of the login field to look up or create.
            email: Email address for a new user.
            first_name: First name for a new user.
            last_name: Last name for a new user.
            password: Password for a new user.
            configure_user: Called with the user, new or existing, before it is
                saved. Use it to set extra fields.

        Returns:
            The existing or newly created superuser.
        """
        user_model = get_user_model()
        # The swappable user model is only typed as AbstractBaseUser, whose manager
        # lacks create_superuser; any model usable with createsuperuser provides it.
        user_manager = cast(
            "UserManager[AbstractUser]",
            user_model._default_manager.db_manager(self.database),
        )
        username_field = cast(str, user_model.USERNAME_FIELD)
        email_field = user_model.get_email_field_name()

        email = email or app_settings.SUPERUSER_EMAIL
        if username_field == email_field:
            username = username or email
        else:
            username = username or app_settings.SUPERUSER_USERNAME

        try:
            superuser = user_manager.get_by_natural_key(username)
        except user_model.DoesNotExist:
            fields: dict[str, Any] = {
                username_field: username,
                "password": password or app_settings.SUPERUSER_PASSWORD,
            }
            optional_fields = {
                email_field: email,
                "first_name": first_name or app_settings.SUPERUSER_FIRST_NAME,
                "last_name": last_name or app_settings.SUPERUSER_LAST_NAME,
            }
            for name, value in optional_fields.items():
                if name not in fields and _has_field(user_model, name):
                    fields[name] = value
            superuser = user_manager.create_superuser(**fields)

        if configure_user is not None:
            configure_user(superuser)
            superuser.save()
        return superuser

    @abstractmethod
    def handle(self) -> None:
        """Create this builder's data.

        Runs inside its own savepoint, so raising (for example with ``assert``)
        rolls back only this builder's changes.
        """

    def should_run(self, *args: Any, **options: Any) -> bool:
        """Return whether this builder should run in the current environment.

        Runs every time by default. Override it to limit the builder, for example
        ``return settings.DEBUG``.

        Args:
            *args: Positional arguments passed to the ``heavy_water`` command.
            **options: The command's parsed options, such as ``wipe``,
                ``verbosity`` and ``database``.
        """
        return True
