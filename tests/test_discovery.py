"""The ordering and selection functions, without the management command."""

import pytest

from heavy_water.discovery import (
    BuilderSelectionError,
    ExcludedDependent,
    match_builders,
    order_builders,
    select_builders,
)
from tests.testapp import fixtures, fixtures_cycle, fixtures_depends
from tests.testapp.fixtures_options import WipeOnly

APP = "tests.testapp"
BUILDERS = order_builders(
    [
        (APP, fixtures_depends.NeedsParent),
        (APP, fixtures_depends.Parent),
        (APP, fixtures.Basic),
        (APP, fixtures_depends.NeedsBasic),
    ]
)


def names(entries: list[tuple[str, type]]) -> list[str]:
    return [builder.__name__ for _, builder in entries]


class TestOrderBuilders:
    def test_moves_dependencies_first(self) -> None:
        assert names(BUILDERS) == ["Parent", "NeedsParent", "Basic", "NeedsBasic"]

    def test_keeps_order_without_dependencies(self) -> None:
        entries = [(APP, fixtures.Basic), (APP, fixtures_depends.Parent)]

        assert order_builders(entries) == entries

    def test_cycle_is_an_error(self) -> None:
        entries = [(APP, fixtures_cycle.First), (APP, fixtures_cycle.Second)]

        with pytest.raises(BuilderSelectionError, match="First -> Second -> First"):
            order_builders(entries)

    def test_missing_dependency_is_an_error(self) -> None:
        with pytest.raises(BuilderSelectionError, match="isn't a discovered builder"):
            order_builders([(APP, fixtures_depends.NeedsBasic)])


class TestSelectBuilders:
    def test_no_filters_selects_everything(self) -> None:
        assert select_builders(BUILDERS) == (BUILDERS, [])

    def test_only_adds_dependencies_and_keeps_order(self) -> None:
        selected, _ = select_builders(
            BUILDERS, only=["testapp.NeedsBasic", "testapp.NeedsParent"]
        )

        assert names(selected) == ["Parent", "NeedsParent", "Basic", "NeedsBasic"]

    def test_exclude_reports_dropped_dependents(self) -> None:
        selected, dependents = select_builders(BUILDERS, exclude=["testapp.Basic"])

        assert names(selected) == ["Parent", "NeedsParent"]
        assert dependents == [
            ExcludedDependent(APP, fixtures_depends.NeedsBasic, (fixtures.Basic,))
        ]

    def test_exclude_applies_after_only(self) -> None:
        selected, dependents = select_builders(
            BUILDERS, only=["testapp.NeedsParent"], exclude=["testapp.Parent"]
        )

        assert selected == []
        assert [d.builder for d in dependents] == [fixtures_depends.NeedsParent]


class TestMatchBuilders:
    def test_app_label_matches_every_builder_in_the_app(self) -> None:
        assert len(match_builders("testapp", BUILDERS)) == 4

    def test_builder_name_matches_one_builder(self) -> None:
        assert match_builders("testapp.Basic", BUILDERS) == [fixtures.Basic]

    def test_only_matches_the_given_builders(self) -> None:
        with pytest.raises(BuilderSelectionError, match="doesn't match any"):
            match_builders("testapp.WipeOnly", [(APP, fixtures.Basic)])

        assert match_builders("testapp", [(APP, WipeOnly)]) == [WipeOnly]

    def test_unknown_app_is_an_error(self) -> None:
        with pytest.raises(BuilderSelectionError, match="No installed app"):
            match_builders("nope", BUILDERS)
