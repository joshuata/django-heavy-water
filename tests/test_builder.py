from typing import Any

import pytest

from heavy_water import BaseDataBuilder
from tests.testapp.fixtures import Basic
from tests.testapp.fixtures_mixed import FailsAssertion, Raises, Skipped
from tests.testapp.models import Record

pytestmark = pytest.mark.django_db


def make(builder_class: type[BaseDataBuilder]) -> BaseDataBuilder:
    return builder_class(
        app_name="tests.testapp",
    )


def test_returns_true_when_it_ran() -> None:
    assert make(Basic)._heavy_water() is True
    assert Record.objects.filter(name="basic").exists()


def test_returns_false_when_skipped() -> None:
    assert make(Skipped)._heavy_water() is False
    assert not Record.objects.exists()


@pytest.mark.parametrize(
    ("builder_class", "error"),
    [(FailsAssertion, AssertionError), (Raises, RuntimeError)],
)
def test_failures_raise_and_roll_back(
    builder_class: type[BaseDataBuilder], error: type[Exception]
) -> None:
    with pytest.raises(error):
        make(builder_class)._heavy_water()
    assert not Record.objects.exists()


def test_runs_by_default_when_debug_is_on(settings: Any) -> None:
    settings.DEBUG = True

    assert make(Basic).should_run() is True


def test_skipped_by_default_when_debug_is_off(settings: Any) -> None:
    settings.DEBUG = False

    assert make(Basic)._heavy_water() is False
    assert not Record.objects.exists()
