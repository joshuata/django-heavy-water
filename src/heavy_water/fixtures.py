"""Base class for data builders run by the ``heavy_water`` management command."""

from __future__ import annotations

import sys
import warnings
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, cast

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AbstractUser, UserManager

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.core.management.base import OutputWrapper
from django.core.management.color import Style, color_style
from django.db import transaction
from django.db.models import Model
from rich.console import Console
from rich.markup import escape

from heavy_water.conf import DEFAULTS, app_settings


def _has_field(model: type[Model], name: str) -> bool:
    """Return whether ``model`` has a field called ``name``."""
    try:
        model._meta.get_field(name)
    except FieldDoesNotExist:
        return False
    return True


def _warn_deprecated(name: str, replacement: str) -> None:
    warnings.warn(
        f"BaseDataBuilder.{name} is deprecated; use {replacement} instead.",
        HeavyWaterDeprecationWarning,
        # Point at the builder code that read the attribute.
        stacklevel=3,
    )


class HeavyWaterDeprecationWarning(FutureWarning):
    """A heavy_water feature that will be removed in a future release.

    A ``FutureWarning`` rather than a ``DeprecationWarning`` so that Python shows
    it by default when builders run under ``manage.py``.
    """


class BaseDataBuilder(ABC):
    """Base class for a unit of seed data.

    Subclass it in an app's ``fixtures`` module (see ``HEAVY_WATER_FIXTURE_MODULE``)
    and implement :meth:`handle`. The ``heavy_water`` command discovers every
    subclass, and runs each one whose :meth:`should_run` returns ``True``.

    Attributes:
        app_name: Name of the app the builder was discovered in.
        console: A Rich console writing to the command's stdout.
        err_console: A Rich console writing to the command's stderr.
        stdout: Deprecated; use ``console``. The command's output stream.
        stderr: Deprecated; use ``err_console``. The command's error stream.
        style: Deprecated; use Rich markup with ``console``. The command's style.
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
        stdout: OutputWrapper | None = None,
        stderr: OutputWrapper | None = None,
        style: Style | None = None,
        database: str | None = None,
        console: Console | None = None,
        err_console: Console | None = None,
    ) -> None:
        self.app_name = app_name
        self._stdout = stdout or OutputWrapper(sys.stdout)
        self._stderr = stderr or OutputWrapper(sys.stderr)
        self._style = style or color_style()
        self.database = database or app_settings.DATABASE
        self.console = console or Console(soft_wrap=True)
        self.err_console = err_console or Console(stderr=True, soft_wrap=True)

    @property
    def stdout(self) -> OutputWrapper:
        _warn_deprecated("stdout", "self.console")
        return self._stdout

    @property
    def stderr(self) -> OutputWrapper:
        _warn_deprecated("stderr", "self.err_console")
        return self._stderr

    @property
    def style(self) -> Style:
        _warn_deprecated("style", "Rich markup with self.console")
        return self._style

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
        name = escape(self.builder_name)
        if not self.should_run(*args, **options):
            self.console.print(f"[dim]{name}: Skipped[/]")
            return False
        try:
            with transaction.atomic(using=self.database):
                self.handle()
        except AssertionError:
            self.err_console.print(
                f"[bold red]{name}: Assertion failed setting up data[/]"
            )
            self.err_console.print("[red]Rolling back transaction[/]")
            raise
        self.console.print(f"[green]{name}: Successfully set up data[/]")
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

        Raises:
            ImproperlyConfigured: If a user would be created with the default
                password while ``DEBUG`` is ``False``.

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
        username_field = user_model.USERNAME_FIELD
        email_field = user_model.get_email_field_name()

        email = email or app_settings.SUPERUSER_EMAIL
        if username_field == email_field:
            username = username or email
        else:
            username = username or app_settings.SUPERUSER_USERNAME

        try:
            superuser = user_manager.get_by_natural_key(username)
        except user_model.DoesNotExist:
            password = password or app_settings.SUPERUSER_PASSWORD
            if password == DEFAULTS["SUPERUSER_PASSWORD"] and not settings.DEBUG:
                raise ImproperlyConfigured(
                    "Refusing to create a superuser with the default password "
                    "while DEBUG is False. Pass password= or set "
                    "HEAVY_WATER_SUPERUSER_PASSWORD."
                ) from None
            fields: dict[str, Any] = {username_field: username, "password": password}
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

        By default, only when ``DEBUG`` is ``True``, so seed data doesn't reach
        production by accident. Override it to run elsewhere, for example
        ``return True`` for data every environment needs.

        Args:
            *args: Positional arguments passed to the ``heavy_water`` command.
            **options: The command's parsed options, such as ``wipe``,
                ``verbosity`` and ``database``.
        """
        return bool(settings.DEBUG)
