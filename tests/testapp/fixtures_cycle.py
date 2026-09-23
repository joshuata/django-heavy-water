from heavy_water import BaseDataBuilder


class First(BaseDataBuilder):
    def handle(self) -> None:
        pass


class Second(BaseDataBuilder):
    depends_on = (First,)

    def handle(self) -> None:
        pass


First.depends_on = (Second,)
