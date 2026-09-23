from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from tests.testapp.fixtures import Basic

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def debug(settings: Any) -> None:
    # The default password is only allowed in development.
    settings.DEBUG = True


@pytest.fixture
def builder() -> Basic:
    return Basic(
        app_name="tests.testapp",
    )


class TestDefaultUserModel:
    def test_creates_superuser_from_defaults(self, builder: Basic) -> None:
        user = builder.get_or_create_superuser()

        assert user.get_username() == "root"
        assert user.email == "root@example.com"
        assert user.first_name == "Root"
        assert user.last_name == "User"
        assert user.is_superuser
        assert user.is_staff
        assert user.check_password("rootroot")

    def test_uses_explicit_arguments(self, builder: Basic) -> None:
        user = builder.get_or_create_superuser(
            username="admin",
            email="admin@example.com",
            first_name="Ada",
            last_name="Admin",
            password="s3cret",
        )

        assert user.get_username() == "admin"
        assert user.email == "admin@example.com"
        assert (user.first_name, user.last_name) == ("Ada", "Admin")
        assert user.check_password("s3cret")

    @override_settings(
        HEAVY_WATER_SUPERUSER_USERNAME="boss",
        HEAVY_WATER_SUPERUSER_PASSWORD="from-settings",
    )
    def test_defaults_come_from_settings(self, builder: Basic) -> None:
        user = builder.get_or_create_superuser()

        assert user.get_username() == "boss"
        assert user.check_password("from-settings")

    def test_returns_existing_user_unchanged(self, builder: Basic) -> None:
        first = builder.get_or_create_superuser()

        second = builder.get_or_create_superuser(email="other@example.com")

        assert second.pk == first.pk
        assert second.email == "root@example.com"
        assert get_user_model().objects.count() == 1

    def test_configure_user_changes_are_saved(self, builder: Basic) -> None:
        builder.get_or_create_superuser()

        def rename(user: AbstractBaseUser) -> None:
            user.first_name = "Renamed"

        user = builder.get_or_create_superuser(configure_user=rename)
        user.refresh_from_db()

        assert user.first_name == "Renamed"


@pytest.mark.django_db(databases=["default", "other"])
def test_uses_the_builders_database() -> None:
    builder = Basic(
        app_name="tests.testapp",
        database="other",
    )

    user = builder.get_or_create_superuser()
    again = builder.get_or_create_superuser()

    assert user._state.db == "other"
    assert again.pk == user.pk
    assert get_user_model().objects.using("other").count() == 1
    assert not get_user_model().objects.using("default").exists()


@pytest.mark.django_db(databases=["default", "other"])
def test_builder_database_defaults_to_the_setting(
    builder: Basic, settings: Any
) -> None:
    settings.HEAVY_WATER_DATABASE = "other"
    fresh = Basic(
        app_name="tests.testapp",
    )

    assert builder.database == "default"
    assert fresh.database == "other"


class TestDefaultPasswordOutsideDebug:
    @pytest.fixture(autouse=True)
    def debug(self, settings: Any) -> None:
        settings.DEBUG = False

    def test_refuses_to_create_with_default_password(self, builder: Basic) -> None:
        with pytest.raises(ImproperlyConfigured, match="default password"):
            builder.get_or_create_superuser()

        assert not get_user_model().objects.exists()

    def test_allows_an_explicit_password(self, builder: Basic) -> None:
        user = builder.get_or_create_superuser(password="s3cret")

        assert user.check_password("s3cret")

    def test_allows_a_password_from_settings(
        self, builder: Basic, settings: Any
    ) -> None:
        settings.HEAVY_WATER_SUPERUSER_PASSWORD = "from-settings"

        user = builder.get_or_create_superuser()

        assert user.check_password("from-settings")

    def test_returns_an_existing_user(self, builder: Basic) -> None:
        existing = builder.get_or_create_superuser(password="s3cret")

        assert builder.get_or_create_superuser().pk == existing.pk


class TestEmailUserModel:
    @pytest.fixture(autouse=True)
    def email_user_model(self, settings: Any) -> None:
        settings.AUTH_USER_MODEL = "testapp.EmailUser"

    def test_uses_email_as_the_identifier(self, builder: Basic) -> None:
        user = builder.get_or_create_superuser()

        assert type(user).__name__ == "EmailUser"
        assert user.get_username() == "root@example.com"
        assert user.is_superuser
        assert user.check_password("rootroot")

    def test_returns_existing_user(self, builder: Basic) -> None:
        first = builder.get_or_create_superuser(email="me@example.com")

        second = builder.get_or_create_superuser(email="me@example.com")

        assert second.pk == first.pk
        assert get_user_model().objects.count() == 1
