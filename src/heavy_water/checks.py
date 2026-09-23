"""System checks for data builders."""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Sequence
from typing import Any

from django.apps import AppConfig
from django.core import checks

from heavy_water.discovery import discover_builders
from heavy_water.fixtures import BaseDataBuilder

# Deprecated builder attribute -> what to use instead.
DEPRECATED_ATTRIBUTES = {
    "stdout": "self.console",
    "stderr": "self.err_console",
    "style": "Rich markup with self.console",
}


def _deprecated_uses(cls: type) -> list[str]:
    """Return the deprecated ``self.<attribute>`` names read in ``cls``'s source."""
    try:
        source = textwrap.dedent(inspect.getsource(cls))
    except (OSError, TypeError):
        return []
    found = {
        node.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
        and node.attr in DEPRECATED_ATTRIBUTES
    }
    return sorted(found)


@checks.register()
def check_deprecated_output(
    app_configs: Sequence[AppConfig] | None, **kwargs: Any
) -> list[checks.CheckMessage]:
    """Warn about builders that use the deprecated ``stdout``/``stderr``/``style``."""
    errors: list[checks.CheckMessage] = []
    seen: set[type] = set()
    for _, builder in discover_builders(app_configs):
        # Check the builder and any base classes of the host project's own.
        for cls in builder.__mro__:
            if (
                cls in seen
                or not issubclass(cls, BaseDataBuilder)
                or cls is BaseDataBuilder
            ):
                continue
            seen.add(cls)
            for attribute in _deprecated_uses(cls):
                errors.append(
                    checks.Warning(
                        f"Uses self.{attribute}, which is deprecated.",
                        hint=f"Use {DEPRECATED_ATTRIBUTES[attribute]} instead.",
                        obj=cls,
                        id="heavy_water.W001",
                    )
                )
    return errors
