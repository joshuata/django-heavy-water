"""Finding the data builders defined in installed apps."""

from __future__ import annotations

from collections.abc import Iterable
from importlib import import_module
from inspect import isabstract, isclass

from django.apps import AppConfig, apps
from django.utils.module_loading import module_has_submodule

from heavy_water.conf import app_settings
from heavy_water.fixtures import BaseDataBuilder


def discover_builders(
    app_configs: Iterable[AppConfig] | None = None,
) -> list[tuple[str, type[BaseDataBuilder]]]:
    """Return ``(app name, builder class)`` for each builder, in run order.

    Searches each app's ``HEAVY_WATER_FIXTURE_MODULE`` submodules, in
    ``INSTALLED_APPS`` order unless ``app_configs`` is given.
    """
    data_builders: list[tuple[str, type[BaseDataBuilder]]] = []
    for app in apps.get_app_configs() if app_configs is None else app_configs:
        for module_name in app_settings.FIXTURE_MODULE:
            if not module_has_submodule(app.module, module_name):
                continue
            module = import_module(f"{app.name}.{module_name}")
            # vars() keeps definition order, so builders run in the order written.
            for member in vars(module).values():
                # Only concrete builders defined here: imported builders run
                # from their own module, and abstract bases (including
                # BaseDataBuilder) can't be instantiated.
                if (
                    isclass(member)
                    and issubclass(member, BaseDataBuilder)
                    and member.__module__ == module.__name__
                    and not isabstract(member)
                ):
                    data_builders.append((app.name, member))

    return data_builders
