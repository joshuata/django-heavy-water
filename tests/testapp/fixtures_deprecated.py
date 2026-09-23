from heavy_water import BaseDataBuilder


class OldStyleBase(BaseDataBuilder):
    """A shared base that uses the deprecated attributes."""

    def report(self) -> None:
        self.stdout.write(self.style.SUCCESS("done"))


class UsesOldBase(OldStyleBase):
    def handle(self) -> None:
        self.report()


class AlsoUsesOldBase(OldStyleBase):
    def handle(self) -> None:
        self.stderr.write("oops")


class NewStyle(BaseDataBuilder):
    def handle(self) -> None:
        self.console.print("done")
