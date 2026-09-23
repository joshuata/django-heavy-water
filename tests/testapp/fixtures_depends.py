from typing import Any

from heavy_water import BaseDataBuilder
from tests.testapp.fixtures import Basic
from tests.testapp.models import Record


def record(name: str) -> None:
    Record.objects.create(name=name)


class NeedsParent(BaseDataBuilder):
    """Defined before its dependency, so it must be moved after it."""

    def handle(self) -> None:
        assert Record.objects.filter(name="parent").exists()
        record("needs-parent")


class Parent(BaseDataBuilder):
    def handle(self) -> None:
        record("parent")


NeedsParent.depends_on = (Parent,)


class NeedsBasic(BaseDataBuilder):
    """Depends on a builder in another module."""

    depends_on = (Basic,)

    def handle(self) -> None:
        assert Record.objects.filter(name="basic").exists()
        record("needs-basic")


class FailingParent(BaseDataBuilder):
    def handle(self) -> None:
        raise RuntimeError("deliberate error")


class NeedsFailingParent(BaseDataBuilder):
    depends_on = (FailingParent,)

    def handle(self) -> None:
        record("needs-failing-parent")


class SkippedParent(BaseDataBuilder):
    def should_run(self, *args: Any, **options: Any) -> bool:
        return False

    def handle(self) -> None:
        record("skipped-parent")


class NeedsSkippedParent(BaseDataBuilder):
    depends_on = (SkippedParent,)

    def handle(self) -> None:
        record("needs-skipped-parent")
