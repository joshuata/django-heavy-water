from io import StringIO

import pytest
from django.core.management.base import OutputWrapper
from django.core.management.color import no_style

from heavy_water import HeavyWaterDeprecationWarning
from tests.testapp.fixtures import Basic


@pytest.fixture
def builder() -> Basic:
    return Basic(
        app_name="tests.testapp",
        stdout=OutputWrapper(StringIO()),
        stderr=OutputWrapper(StringIO()),
        style=no_style(),
    )


@pytest.mark.parametrize(
    ("attribute", "replacement"),
    [
        ("stdout", "self.console"),
        ("stderr", "self.err_console"),
        ("style", "Rich markup with self.console"),
    ],
)
def test_old_output_attributes_warn(
    builder: Basic, attribute: str, replacement: str
) -> None:
    with pytest.warns(
        HeavyWaterDeprecationWarning,
        match=f"BaseDataBuilder.{attribute} is deprecated; use {replacement}",
    ) as record:
        getattr(builder, attribute)

    # The warning points at the code that read the attribute, not heavy_water.
    assert record[0].filename == __file__


def test_old_output_attributes_still_work() -> None:
    stream = StringIO()
    builder = Basic(app_name="tests.testapp", stdout=OutputWrapper(stream))

    with pytest.warns(HeavyWaterDeprecationWarning):
        builder.stdout.write("still works")

    assert stream.getvalue() == "still works\n"


def test_passing_old_output_arguments_does_not_warn(builder: Basic) -> None:
    Basic(app_name="tests.testapp", stdout=OutputWrapper(StringIO()))
