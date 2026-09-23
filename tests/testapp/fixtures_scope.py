from heavy_water import BaseDataBuilder
from tests.testapp.fixtures import Basic  # noqa: F401  (imported, not defined here)
from tests.testapp.models import Record


class SharedBase(BaseDataBuilder):
    """An abstract base: it doesn't implement handle()."""

    def record(self, name: str) -> None:
        Record.objects.using(self.database).create(name=name)


class UsesSharedBase(SharedBase):
    def handle(self) -> None:
        self.record("uses-shared-base")
