from io import StringIO
from typing import Any

import pytest
from django.core.management import CommandError, call_command

from tests.testapp.models import Record

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fixture_modules(settings: Any) -> None:
    settings.HEAVY_WATER_FIXTURE_MODULE = ["fixtures_depends", "fixtures"]


def run(**options: Any) -> str:
    stdout = StringIO()
    call_command("heavy_water", stdout=stdout, stderr=StringIO(), **options)
    return stdout.getvalue()


def listed(**options: Any) -> list[str]:
    """The builder names --list shows, in order."""
    lines = run(list=True, **options).splitlines()
    return [
        line.split(" - ")[1].split(" ")[0]
        for line in lines
        if line[:4] in ("├── ", "└── ")
    ]


class TestOnly:
    def test_runs_the_builder_and_its_dependencies(self) -> None:
        run(only=["testapp.NeedsParent"])

        assert list(Record.objects.order_by("pk").values_list("name", flat=True)) == [
            "parent",
            "needs-parent",
        ]

    def test_can_be_repeated(self) -> None:
        assert listed(only=["testapp.Parent", "testapp.NeedsBasic"]) == [
            "Parent",
            "Basic",
            "NeedsBasic",
        ]

    def test_app_label_selects_the_whole_app(self) -> None:
        assert len(listed(only=["testapp"])) == 8


class TestExclude:
    def test_removes_the_builder(self) -> None:
        assert "SkippedParent" not in listed(exclude=["testapp.SkippedParent"])

    def test_removes_builders_that_depend_on_it(self) -> None:
        output = run(list=True, exclude=["testapp.Basic"])

        assert "tests.testapp - NeedsBasic: Excluded, it depends on Basic" in output
        assert "NeedsBasic" not in listed(exclude=["testapp.Basic"])
        assert "NeedsParent" in listed(exclude=["testapp.Basic"])

    def test_applies_after_only(self) -> None:
        assert listed(only=["testapp.NeedsParent"], exclude=["testapp.Parent"]) == []

    def test_can_exclude_builders_outside_only(self) -> None:
        assert listed(only=["testapp.Parent"], exclude=["testapp.Basic"]) == ["Parent"]

    def test_run_skips_excluded_builders(self) -> None:
        run(
            exclude=[
                "testapp.FailingParent",
                "testapp.SkippedParent",
                "testapp.NeedsBasic",
            ]
        )

        assert set(Record.objects.values_list("name", flat=True)) == {
            "parent",
            "needs-parent",
            "basic",
        }


@pytest.mark.parametrize("option", ["only", "exclude"])
def test_unknown_app_is_an_error(option: str) -> None:
    with pytest.raises(CommandError, match="No installed app with label 'nope'"):
        run(**{option: ["nope.Basic"]})


@pytest.mark.parametrize("option", ["only", "exclude"])
def test_unknown_builder_is_an_error(option: str) -> None:
    with pytest.raises(CommandError, match="'testapp.Nope' doesn't match any"):
        run(**{option: ["testapp.Nope"]})
