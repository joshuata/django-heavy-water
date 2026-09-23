from importlib import import_module
from inspect import isabstract, isclass
from traceback import format_exception
from typing import Any, Literal

from django.apps import apps
from django.conf import settings
from django.core.management.base import CommandError, CommandParser
from django.core.management.commands.flush import Command as FlushCommand
from django.db import transaction
from django.utils.module_loading import module_has_submodule

from heavy_water import BaseDataBuilder
from heavy_water.conf import app_settings

Result = Literal["ran", "skipped", "failed"]


class Command(FlushCommand):
    help = "Runs the data builders for the current environment"
    requires_migrations_checks = True

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--wipe",
            action="store_true",
            help="Flush the database before running the builders.",
        )
        # None means "not given", so HEAVY_WATER_DATABASE can apply. flush's help
        # text for --database would otherwise claim it defaults to "default".
        parser.set_defaults(database=None)
        for action in parser._actions:
            if action.dest == "database":
                action.help = (
                    "Nominates a database to seed (and flush, with --wipe). "
                    'Defaults to HEAVY_WATER_DATABASE, or the "default" database.'
                )

    def handle(self, *args: Any, **options: Any) -> None:
        # Commit whatever succeeded before reporting failure, so a single bad
        # builder doesn't roll back the others.
        database = options.get("database") or app_settings.DATABASE
        if database not in settings.DATABASES:
            raise CommandError(
                f"Unknown database {database!r}; expected one of {sorted(settings.DATABASES)}"
            )
        options["database"] = database
        with transaction.atomic(using=database):
            failures = self._build(*args, **options)
        if failures:
            raise CommandError(
                f"{len(failures)} data builder(s) failed: {', '.join(failures)}"
            )

    def _build(self, *args: Any, **options: Any) -> list[str]:
        # Order first, so a dependency error stops the command before --wipe.
        builders = self._order_builders(self._discover_builders())
        if options.get("wipe"):
            super().handle(*args, **options)

        results: dict[type[BaseDataBuilder], Result] = {}
        failures: list[str] = []
        for app_name, builder in builders:
            name = f"{app_name} - {builder.__name__}"
            results[builder] = self._run_builder(
                name, app_name, builder, results, *args, **options
            )
            if results[builder] == "failed":
                failures.append(name)
        return failures

    def _run_builder(
        self,
        name: str,
        app_name: str,
        builder: type[BaseDataBuilder],
        results: dict[type[BaseDataBuilder], Result],
        *args: Any,
        **options: Any,
    ) -> Result:
        unmet = [dep for dep in builder.depends_on if results[dep] != "ran"]
        if unmet:
            deps = ", ".join(dep.__name__ for dep in unmet)
            if any(results[dep] == "failed" for dep in unmet):
                self.stderr.write(
                    self.style.ERROR(f"{name}: Not run, a dependency failed ({deps})")
                )
                return "failed"
            self.stdout.write(f"{name}: Skipped, a dependency was skipped ({deps})")
            return "skipped"

        try:
            obj = builder(
                app_name=app_name,
                stdout=self.stdout,
                stderr=self.stderr,
                style=self.style,
                database=options["database"],
            )
            return "ran" if obj._heavy_water(*args, **options) else "skipped"
        except Exception as ex:
            output = "".join(format_exception(ex))
            self.stderr.write(self.style.ERROR_OUTPUT(output))
            return "failed"

    def _order_builders(
        self, builders: list[tuple[str, type[BaseDataBuilder]]]
    ) -> list[tuple[str, type[BaseDataBuilder]]]:
        """Move each builder's ``depends_on`` ahead of it, otherwise keeping order."""
        app_names = {builder: app_name for app_name, builder in builders}
        ordered: list[tuple[str, type[BaseDataBuilder]]] = []
        visiting: list[type[BaseDataBuilder]] = []

        def visit(builder: type[BaseDataBuilder]) -> None:
            if builder in visiting:
                cycle = visiting[visiting.index(builder) :] + [builder]
                raise CommandError(
                    "Builder dependency cycle: "
                    + " -> ".join(dep.__name__ for dep in cycle)
                )
            if any(done is builder for _, done in ordered):
                return
            visiting.append(builder)
            for dep in builder.depends_on:
                if dep not in app_names:
                    raise CommandError(
                        f"{builder.__name__} depends on {dep.__module__}.{dep.__name__}, "
                        "which isn't a discovered builder"
                    )
                visit(dep)
            visiting.pop()
            ordered.append((app_names[builder], builder))

        for _, builder in builders:
            visit(builder)
        return ordered

    def _discover_builders(self) -> list[tuple[str, type[BaseDataBuilder]]]:
        data_builders: list[tuple[str, type[BaseDataBuilder]]] = []
        for app in apps.get_app_configs():
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
