from io import StringIO
from typing import Any

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from tests.testapp.models import Record

pytestmark = pytest.mark.django_db


def dry_run(**options: Any) -> str:
    stdout = StringIO()
    call_command(
        "heavy_water", dry_run=True, stdout=stdout, stderr=StringIO(), **options
    )
    return stdout.getvalue()


def test_runs_builders_then_rolls_back() -> None:
    output = dry_run()

    assert "tests.testapp - Basic: Successfully set up data" in output
    assert "Dry run: all database changes were rolled back." in output
    assert not Record.objects.exists()


@override_settings(HEAVY_WATER_FIXTURE_MODULE=["fixtures_mixed"])
def test_still_reports_failures() -> None:
    with pytest.raises(CommandError, match="2 data builder"):
        dry_run()

    assert not Record.objects.exists()


def test_cannot_be_combined_with_wipe() -> None:
    Record.objects.create(name="kept")

    with pytest.raises(
        CommandError, match="--wipe and --dry-run can't be used together"
    ):
        dry_run(wipe=True, interactive=False)

    assert list(Record.objects.values_list("name", flat=True)) == ["kept"]
