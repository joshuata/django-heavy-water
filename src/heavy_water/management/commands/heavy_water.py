import sys
from typing import Any, Literal

from django.conf import settings
from django.core import checks
from django.core.management.base import CommandError, CommandParser
from django.core.management.commands.flush import Command as FlushCommand
from django.db import transaction
from django_rich.management import RichCommand
from rich.console import Console
from rich.markup import escape
from rich.tree import Tree

from heavy_water import BaseDataBuilder
from heavy_water.checks import check_deprecated_output
from heavy_water.conf import app_settings
from heavy_water.discovery import (
    BuilderEntry,
    BuilderSelectionError,
    discover_builders,
    order_builders,
    select_builders,
)

Result = Literal["ran", "skipped", "failed"]

# Registered here rather than in AppConfig.ready(), so only this command runs it
# (Django runs a command's system checks after importing its module).
checks.register(check_deprecated_output, "heavy_water")


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
        # Wrap long labels rather than cropping them at the console width.
        self.console.print(tree, soft_wrap=False)

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

    def _selected_builders(self, **options: Any) -> list[BuilderEntry]:
        """Return the builders to run, in order, after ``--only`` and ``--exclude``."""
        try:
            selected, dependents = select_builders(
                order_builders(discover_builders()),
                only=options.get("only") or [],
                exclude=options.get("exclude") or [],
            )
        except BuilderSelectionError as ex:
            raise CommandError(str(ex)) from None
        for app_name, builder, because in dependents:
            names = escape(", ".join(dep.__name__ for dep in because))
            self.console.print(
                f"[dim]{escape(f'{app_name} - {builder.__name__}')}: "
                f"Excluded, it depends on {names}[/]"
            )
        return selected
