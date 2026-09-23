from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.test import override_settings

from tests.testapp.models import Record

pytestmark = pytest.mark.django_db


def list_builders(**options: Any) -> str:
    stdout = StringIO()
    call_command("heavy_water", list=True, stdout=stdout, stderr=StringIO(), **options)
    return stdout.getvalue()


@override_settings(HEAVY_WATER_FIXTURE_MODULE=["fixtures_depends", "fixtures"])
def test_lists_builders_in_run_order_with_dependencies() -> None:
    assert list_builders() == (
        "Data builders, in run order\n"
        "├── 1. tests.testapp - Parent\n"
        "├── 2. tests.testapp - NeedsParent\n"
        "│   └── depends on 1. tests.testapp - Parent\n"
        "├── 3. tests.testapp - Basic\n"
        "├── 4. tests.testapp - NeedsBasic\n"
        "│   └── depends on 3. tests.testapp - Basic\n"
        "├── 5. tests.testapp - FailingParent\n"
        "├── 6. tests.testapp - NeedsFailingParent\n"
        "│   └── depends on 5. tests.testapp - FailingParent\n"
        "├── 7. tests.testapp - SkippedParent (skipped)\n"
        "└── 8. tests.testapp - NeedsSkippedParent (skipped, a dependency is skipped)\n"
        "    └── depends on 7. tests.testapp - SkippedParent (skipped)\n"
    )


@override_settings(HEAVY_WATER_FIXTURE_MODULE=["fixtures_depends", "fixtures"])
def test_skipped_builders_are_dim() -> None:
    output = list_builders(force_color=True)

    assert "\x1b[2m7. tests.testapp - SkippedParent (skipped)" in output
    assert "\x1b[2m1. tests.testapp - Parent" not in output


@override_settings(HEAVY_WATER_FIXTURE_MODULE=["fixtures_options", "fixtures"])
def test_should_run_sees_the_command_options() -> None:
    assert "WipeOnly (skipped)" in list_builders()
    assert "WipeOnly (skipped)" not in list_builders(wipe=True)


@override_settings(HEAVY_WATER_FIXTURE_MODULE=["fixtures", "fixtures_mixed"])
def test_does_not_run_or_wipe_anything() -> None:
    Record.objects.create(name="kept")

    list_builders(wipe=True, interactive=False)

    assert list(Record.objects.values_list("name", flat=True)) == ["kept"]


@override_settings(HEAVY_WATER_FIXTURE_MODULE=["does_not_exist"])
def test_reports_when_there_are_no_builders() -> None:
    assert list_builders() == "No data builders found.\n"


@override_settings(HEAVY_WATER_FIXTURE_MODULE=["fixtures_should_run_error"])
def test_should_run_errors_are_shown_as_skipped() -> None:
    # Long labels wrap instead of being cropped, so compare without line breaks.
    output = " ".join(list_builders().split())

    assert (
        "1. tests.testapp - ShouldRunRaises "
        "(skipped, should_run() raised ValueError('boom'))" in output
    )
