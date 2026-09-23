import os
import subprocess
import sys
from io import StringIO

import pytest
from django.apps import apps
from django.core import checks
from django.core.management import call_command
from django.test import override_settings

from heavy_water import BaseDataBuilder
from heavy_water.checks import _deprecated_uses, check_deprecated_output
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


@pytest.mark.django_db
@override_settings(HEAVY_WATER_FIXTURE_MODULE=["fixtures_deprecated"])
def test_runs_before_the_heavy_water_command() -> None:
    # call_command() skips system checks unless asked; manage.py runs them.
    stderr = StringIO()
    call_command(
        "heavy_water", list=True, skip_checks=False, stdout=StringIO(), stderr=stderr
    )

    assert "(heavy_water.W001) Uses self.stdout, which is deprecated." in (
        stderr.getvalue()
    )


@override_settings(HEAVY_WATER_FIXTURE_MODULE=["fixtures_deprecated"])
def test_command_module_registers_it_with_a_tag() -> None:
    import heavy_water.management.commands.heavy_water  # noqa: F401

    assert "heavy_water.W001" in {
        message.id for message in checks.run_checks(tags=["heavy_water"])
    }


def test_loading_the_app_does_not_register_it() -> None:
    # A fresh process, since this one may already have imported the command.
    code = (
        "import django; django.setup();"
        "from django.core.checks import registry;"
        "print(any(c.__name__ == 'check_deprecated_output'"
        " for c in registry.registry.get_checks()))"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "tests.settings"},
    )

    assert result.stdout.strip() == "False"


def test_classes_without_source_are_skipped() -> None:
    # Created at run time, so inspect.getsource() can't find its source.
    dynamic = type("Dynamic", (BaseDataBuilder,), {"handle": lambda self: None})

    assert _deprecated_uses(dynamic) == []
