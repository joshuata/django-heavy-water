from django.apps import apps
from django.core import checks
from django.test import override_settings

from heavy_water.checks import check_deprecated_output
from tests.testapp import fixtures_deprecated


def test_default_fixtures_have_no_warnings() -> None:
    assert check_deprecated_output(None) == []


@override_settings(HEAVY_WATER_FIXTURE_MODULE=["fixtures_deprecated"])
def test_warns_once_per_class_and_attribute() -> None:
    messages = check_deprecated_output(None)

    assert [(m.obj, m.msg, m.hint) for m in messages] == [
        (
            fixtures_deprecated.OldStyleBase,
            "Uses self.stdout, which is deprecated.",
            "Use self.console instead.",
        ),
        (
            fixtures_deprecated.OldStyleBase,
            "Uses self.style, which is deprecated.",
            "Use Rich markup with self.console instead.",
        ),
        (
            fixtures_deprecated.AlsoUsesOldBase,
            "Uses self.stderr, which is deprecated.",
            "Use self.err_console instead.",
        ),
    ]
    assert {m.id for m in messages} == {"heavy_water.W001"}
    assert all(isinstance(m, checks.Warning) for m in messages)


@override_settings(HEAVY_WATER_FIXTURE_MODULE=["fixtures_deprecated"])
def test_only_checks_the_given_apps() -> None:
    assert check_deprecated_output([apps.get_app_config("auth")]) == []


@override_settings(HEAVY_WATER_FIXTURE_MODULE=["fixtures_deprecated"])
def test_is_registered_with_django() -> None:
    ids = {message.id for message in checks.run_checks()}

    assert "heavy_water.W001" in ids
