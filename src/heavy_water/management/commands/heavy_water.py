import sys
from typing import Any, Literal

from django.apps import apps
from django.conf import settings
from django.core.management.base import CommandError, CommandParser
from django.core.management.commands.flush import Command as FlushCommand
from django.db import transaction
from django_rich.management import RichCommand
from rich.console import Console
from rich.markup import escape
from rich.tree import Tree

from heavy_water import BaseDataBuilder
from heavy_water.conf import app_settings
from heavy_water.discovery import discover_builders

Result = Literal["ran", "skipped", "failed"]


class Command(RichCommand, FlushCommand):
    help = "Runs the data builders for the current environment"
    requires_migrations_checks = True

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--wipe",
            action="store_true",
            help="Flush the database before running the builders.",
        )
        parser.add_argument(
            "--only",
            action="append",
            default=[],
            metavar="APP_LABEL[.BUILDER]",
            help="Run only these builders (and their dependencies). Repeatable.",
        )
        parser.add_argument(
            "--exclude",
            action="append",
            default=[],
            metavar="APP_LABEL[.BUILDER]",
            help="Don't run these builders, or builders that depend on them. Repeatable.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run the builders, then roll back all their database changes.",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List the builders in the order they would run, without running them.",
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

    def make_rich_console(self, **kwargs: Any) -> Console:
        # Keep status lines whole instead of wrapping them at the console width.
        return super().make_rich_console(**kwargs, soft_wrap=True)

    def handle(self, *args: Any, **options: Any) -> None:
        # RichCommand only sets up stdout; mirror it for stderr.
        force_terminal = (
            False if options["no_color"] else True if options["force_color"] else None
        )
        self.err_console = self.make_rich_console(
            file=options.get("stderr") or sys.stderr,
            force_terminal=force_terminal,
        )
        database = options.get("database") or app_settings.DATABASE
        if database not in settings.DATABASES:
            raise CommandError(
                f"Unknown database {database!r}; expected one of {sorted(settings.DATABASES)}"
            )
        options["database"] = database
        if options["list"]:
            self._list(*args, **options)
            return
        dry_run = options["dry_run"]
        if dry_run and options["wipe"]:
            raise CommandError("--wipe and --dry-run can't be used together.")
        # Commit whatever succeeded (unless this is a dry run) before reporting
        # failure, so a single bad builder doesn't roll back the others.
        with transaction.atomic(using=database):
            failures = self._build(*args, **options)
            if dry_run:
                transaction.set_rollback(True, using=database)
        if dry_run:
            self.console.print(
                "[yellow]Dry run: all database changes were rolled back.[/]"
            )
        if failures:
            raise CommandError(
                f"{len(failures)} data builder(s) failed: {', '.join(failures)}"
            )

    def _build(self, *args: Any, **options: Any) -> list[str]:
        # Order first, so a dependency error stops the command before --wipe.
        builders = self._selected_builders(**options)
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
            deps = escape(", ".join(dep.__name__ for dep in unmet))
            if any(results[dep] == "failed" for dep in unmet):
                self.err_console.print(
                    f"[bold red]{escape(name)}: Not run, a dependency failed ({deps})[/]"
                )
                return "failed"
            self.console.print(
                f"[dim]{escape(name)}: Skipped, a dependency was skipped ({deps})[/]"
            )
            return "skipped"

        try:
            obj = self._make_builder(app_name, builder, options["database"])
            return "ran" if obj._heavy_water(*args, **options) else "skipped"
        except Exception:
            self.err_console.print_exception()
            return "failed"

    def _make_builder(
        self, app_name: str, builder: type[BaseDataBuilder], database: str
    ) -> BaseDataBuilder:
        return builder(
            app_name=app_name,
            stdout=self.stdout,
            stderr=self.stderr,
            style=self.style,
            database=database,
            console=self.console,
            err_console=self.err_console,
        )

    def _list(self, *args: Any, **options: Any) -> None:
        """Print the builders as a tree in run order, with their dependencies."""
        builders = self._selected_builders(**options)
        if not builders:
            self.console.print("No data builders found.")
            return

        labels: dict[type[BaseDataBuilder], str] = {}
        skipped: set[type[BaseDataBuilder]] = set()
        tree = Tree("[bold]Data builders[/], in run order")
        for index, (app_name, builder) in enumerate(builders, start=1):
            label = f"{index}. {escape(f'{app_name} - {builder.__name__}')}"
            note = self._list_note(app_name, builder, skipped, *args, **options)
            if note is not None:
                skipped.add(builder)
                label = f"[dim]{label} ({escape(note)})[/]"
            labels[builder] = label
            node = tree.add(label)
            for dep in builder.depends_on:
                node.add(f"[dim]depends on[/] {labels[dep]}")
        self.console.print(tree)

    def _list_note(
        self,
        app_name: str,
        builder: type[BaseDataBuilder],
        skipped: set[type[BaseDataBuilder]],
        *args: Any,
        **options: Any,
    ) -> str | None:
        """Return why ``builder`` would be skipped, or ``None`` if it would run."""
        if any(dep in skipped for dep in builder.depends_on):
            return "skipped, a dependency is skipped"
        try:
            obj = self._make_builder(app_name, builder, options["database"])
            if not obj.should_run(*args, **options):
                return "skipped"
        except Exception as ex:
            return f"skipped, should_run() raised {ex!r}"
        return None

    def _selected_builders(
        self, **options: Any
    ) -> list[tuple[str, type[BaseDataBuilder]]]:
        """Return the builders to run, in order, after ``--only`` and ``--exclude``."""
        builders = all_builders = self._order_builders(self._discover_builders())
        only: list[str] = options.get("only") or []
        exclude: list[str] = options.get("exclude") or []

        if only:
            keep: set[type[BaseDataBuilder]] = set()
            pending = [b for spec in only for b in self._match(spec, all_builders)]
            while pending:
                builder = pending.pop()
                if builder not in keep:
                    keep.add(builder)
                    pending.extend(builder.depends_on)
            builders = [entry for entry in builders if entry[1] in keep]

        if exclude:
            dropped = {b for spec in exclude for b in self._match(spec, all_builders)}
            # Dependencies come first in run order, so one pass finds every
            # builder that depends, directly or not, on an excluded one.
            for app_name, builder in builders:
                deps = [dep for dep in builder.depends_on if dep in dropped]
                if builder not in dropped and deps:
                    dropped.add(builder)
                    names = escape(", ".join(dep.__name__ for dep in deps))
                    self.console.print(
                        f"[dim]{escape(f'{app_name} - {builder.__name__}')}: "
                        f"Excluded, it depends on {names}[/]"
                    )
            builders = [entry for entry in builders if entry[1] not in dropped]

        return builders

    def _match(
        self, spec: str, builders: list[tuple[str, type[BaseDataBuilder]]]
    ) -> list[type[BaseDataBuilder]]:
        """Return the builders matching ``app_label`` or ``app_label.BuilderName``."""
        label, _, name = spec.partition(".")
        try:
            app_name = apps.get_app_config(label).name
        except LookupError:
            raise CommandError(
                f"No installed app with label {label!r} ({spec!r})."
            ) from None
        matches = [
            builder
            for builder_app, builder in builders
            if builder_app == app_name and (not name or builder.__name__ == name)
        ]
        if not matches:
            raise CommandError(f"{spec!r} doesn't match any data builders.")
        return matches

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
        return discover_builders()
