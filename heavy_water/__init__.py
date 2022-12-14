from typing import Any
from abc import ABC, abstractmethod
from traceback import print_exc
from django.db import transaction
from django.core.management.color import Style
from django.core.management.base import OutputWrapper


class BaseDataBuilder(ABC):
    def __init__(
        self, app_name: str, stdout: OutputWrapper, stderr: OutputWrapper, style: Style
    ) -> None:
        self.app_name = app_name
        self.stdout = stdout
        self.stderr = stderr
        self.style = style

    def _heavy_water(self, *args: Any, **kwargs: Any) -> Any:
        try:
            with transaction.atomic():
                self.handle()
                self.stdout.write(
                    self.style.SUCCESS(f"Successfully set up data for {self.app_name}")
                )
        except AssertionError as ex:
            self.stderr.write(
                self.style.ERROR(
                    f"Assertion failed setting up data for {self.app_name}."
                )
            )
            print_exc()  # TODO: print to self.stderr
            self.stderr.write(self.style.ERROR(f"Rolling back transaction"))

    @abstractmethod
    def handle(self):
        pass
