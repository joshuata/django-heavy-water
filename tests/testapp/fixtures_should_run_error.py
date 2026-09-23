from typing import Any

from heavy_water import BaseDataBuilder


class ShouldRunRaises(BaseDataBuilder):
    def should_run(self, *args: Any, **options: Any) -> bool:
        raise ValueError("boom")

    def handle(self) -> None:
        pass
