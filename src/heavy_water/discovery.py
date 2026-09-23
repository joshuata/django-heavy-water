"""Finding, ordering and selecting the data builders defined in installed apps."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from importlib import import_module
from inspect import isabstract, isclass
from typing import NamedTuple, TypeAlias

from django.apps import AppConfig, apps
from django.utils.module_loading import module_has_submodule

from heavy_water.conf import app_settings
from heavy_water.fixtures import BaseDataBuilder

#: An app name and a builder class discovered in it.
BuilderEntry: TypeAlias = tuple[str, type[BaseDataBuilder]]


class BuilderSelectionError(Exception):
    """The builders can't be ordered or selected as asked."""


class ExcludedDependent(NamedTuple):
    """A builder excluded because it depends on an excluded builder."""

    app_name: str
    builder: type[BaseDataBuilder]
    #: The excluded builders it depends on directly.
    because: tuple[type[BaseDataBuilder], ...]


def discover_builders(
    app_configs: Iterable[AppConfig] | None = None,
) -> list[BuilderEntry]:
    """Return ``(app name, builder class)`` for each builder, in discovery order.

    Searches each app's ``HEAVY_WATER_FIXTURE_MODULE`` submodules, in
    ``INSTALLED_APPS`` order unless ``app_configs`` is given.
    """
    data_builders: list[BuilderEntry] = []
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


def order_builders(builders: Sequence[BuilderEntry]) -> list[BuilderEntry]:
    """Move each builder's ``depends_on`` ahead of it, otherwise keeping order.

    Raises:
        BuilderSelectionError: If the dependencies form a cycle, or a dependency
            isn't one of ``builders``.
    """
    app_names = {builder: app_name for app_name, builder in builders}
    ordered: list[BuilderEntry] = []
    visiting: list[type[BaseDataBuilder]] = []

    def visit(builder: type[BaseDataBuilder]) -> None:
        if builder in visiting:
            cycle = visiting[visiting.index(builder) :] + [builder]
            raise BuilderSelectionError(
                "Builder dependency cycle: "
                + " -> ".join(dep.__name__ for dep in cycle)
            )
        if any(done is builder for _, done in ordered):
            return
        visiting.append(builder)
        for dep in builder.depends_on:
            if dep not in app_names:
                raise BuilderSelectionError(
                    f"{builder.__name__} depends on {dep.__module__}.{dep.__name__}, "
                    "which isn't a discovered builder"
                )
            visit(dep)
        visiting.pop()
        ordered.append((app_names[builder], builder))

    for _, builder in builders:
        visit(builder)
    return ordered


def select_builders(
    builders: Sequence[BuilderEntry],
    only: Sequence[str] = (),
    exclude: Sequence[str] = (),
) -> tuple[list[BuilderEntry], list[ExcludedDependent]]:
    """Apply ``--only`` and ``--exclude`` to builders already in run order.

    ``only`` keeps the matching builders and, transitively, their dependencies.
    ``exclude`` then drops the matching builders and anything that depends on
    them. Both take ``app_label`` or ``app_label.BuilderName`` specs, matched
    against all of ``builders``.

    Returns:
        The selected builders, still in order, and the builders excluded only
        because they depend on an excluded one.

    Raises:
        BuilderSelectionError: If a spec names an unknown app or matches no
            builders.
    """
    selected = list(builders)

    if only:
        keep: set[type[BaseDataBuilder]] = set()
        pending = [b for spec in only for b in match_builders(spec, builders)]
        while pending:
            builder = pending.pop()
            if builder not in keep:
                keep.add(builder)
                pending.extend(builder.depends_on)
        selected = [entry for entry in selected if entry[1] in keep]

    dependents: list[ExcludedDependent] = []
    if exclude:
        dropped = {b for spec in exclude for b in match_builders(spec, builders)}
        # Dependencies come first in run order, so one pass finds every
        # builder that depends, directly or not, on an excluded one.
        for app_name, builder in selected:
            because = tuple(dep for dep in builder.depends_on if dep in dropped)
            if builder not in dropped and because:
                dropped.add(builder)
                dependents.append(ExcludedDependent(app_name, builder, because))
        selected = [entry for entry in selected if entry[1] not in dropped]

    return selected, dependents


def match_builders(
    spec: str, builders: Sequence[BuilderEntry]
) -> list[type[BaseDataBuilder]]:
    """Return the builders matching ``app_label`` or ``app_label.BuilderName``.

    Raises:
        BuilderSelectionError: If the app label isn't installed, or nothing
            matches.
    """
    label, _, name = spec.partition(".")
    try:
        app_name = apps.get_app_config(label).name
    except LookupError:
        raise BuilderSelectionError(
            f"No installed app with label {label!r} ({spec!r})."
        ) from None
    matches = [
        builder
        for builder_app, builder in builders
        if builder_app == app_name and (not name or builder.__name__ == name)
    ]
    if not matches:
        raise BuilderSelectionError(f"{spec!r} doesn't match any data builders.")
    return matches
