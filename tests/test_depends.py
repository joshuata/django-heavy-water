from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from heavy_water.discovery import discover_builders, order_builders
from tests.testapp import fixtures, fixtures_depends
from tests.testapp.models import Record

pytestmark = pytest.mark.django_db

MODULES = ["fixtures_depends", "fixtures"]


def names() -> list[str]:
    return list(Record.objects.order_by("pk").values_list("name", flat=True))


@override_settings(HEAVY_WATER_FIXTURE_MODULE=MODULES)
def test_dependencies_run_first() -> None:
    builders = order_builders(discover_builders())

    assert [builder for _, builder in builders] == [
        fixtures_depends.Parent,
        fixtures_depends.NeedsParent,
        fixtures.Basic,
        fixtures_depends.NeedsBasic,
        fixtures_depends.FailingParent,
        fixtures_depends.NeedsFailingParent,
        fixtures_depends.SkippedParent,
        fixtures_depends.NeedsSkippedParent,
    ]


@override_settings(HEAVY_WATER_FIXTURE_MODULE=MODULES)
def test_dependents_see_their_dependencies_data() -> None:
    with pytest.raises(CommandError):
        call_command("heavy_water", stdout=StringIO(), stderr=StringIO())

    assert names() == ["parent", "needs-parent", "basic", "needs-basic"]


@override_settings(HEAVY_WATER_FIXTURE_MODULE=MODULES)
def test_failed_dependency_fails_dependents() -> None:
    stderr = StringIO()
    with pytest.raises(CommandError) as excinfo:
        call_command("heavy_water", stdout=StringIO(), stderr=stderr)

    assert str(excinfo.value) == (
        "2 data builder(s) failed: tests.testapp - FailingParent, "
        "tests.testapp - NeedsFailingParent"
    )
    assert (
        "tests.testapp - NeedsFailingParent: Not run, a dependency failed "
        "(FailingParent)" in stderr.getvalue()
    )


@override_settings(HEAVY_WATER_FIXTURE_MODULE=MODULES)
def test_skipped_dependency_skips_dependents() -> None:
    stdout = StringIO()
    with pytest.raises(CommandError):
        call_command("heavy_water", stdout=stdout, stderr=StringIO())

    assert "needs-skipped-parent" not in names()
    assert (
        "tests.testapp - NeedsSkippedParent: Skipped, a dependency was skipped "
        "(SkippedParent)" in stdout.getvalue()
    )


@override_settings(HEAVY_WATER_FIXTURE_MODULE=["fixtures", "fixtures_cycle"])
def test_cycle_is_an_error_before_anything_runs() -> None:
    with pytest.raises(
        CommandError, match="dependency cycle: First -> Second -> First"
    ):
        call_command("heavy_water", stdout=StringIO(), stderr=StringIO())

    assert names() == []


@override_settings(HEAVY_WATER_FIXTURE_MODULE=["fixtures_missing_dep"])
def test_undiscovered_dependency_is_an_error() -> None:
    with pytest.raises(
        CommandError,
        match="NeedsUndiscovered depends on tests.testapp.fixtures_options.WipeOnly",
    ):
        call_command("heavy_water", stdout=StringIO(), stderr=StringIO())


@override_settings(HEAVY_WATER_FIXTURE_MODULE=["fixtures", "fixtures_cycle"])
def test_dependency_errors_happen_before_wipe() -> None:
    Record.objects.create(name="kept")

    with pytest.raises(CommandError):
        call_command(
            "heavy_water",
            wipe=True,
            interactive=False,
            stdout=StringIO(),
            stderr=StringIO(),
        )

    assert names() == ["kept"]
