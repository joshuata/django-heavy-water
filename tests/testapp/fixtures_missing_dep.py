from heavy_water import BaseDataBuilder
from tests.testapp.fixtures_options import WipeOnly


class NeedsUndiscovered(BaseDataBuilder):
    depends_on = (WipeOnly,)

    def handle(self) -> None:
        pass
