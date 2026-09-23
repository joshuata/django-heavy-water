# Changelog

All notable changes to django-heavy-water. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [semantic versioning](https://semver.org/) (before 1.0, a minor version can include breaking changes).

## Unreleased

### Changed

- Development only: ruff is installed as a dev dependency instead of by mise, and mise re-syncs `.venv` automatically when `pyproject.toml` or `uv.lock` change.
- Development only: commit messages must follow Conventional Commits, enforced by a `commit-msg` hook.

## 0.2.2 - 2026-09-23

### Upgrading from 0.2.1

- **Builder output now uses Rich.** Print with `self.console` and `self.err_console`, which accept [Rich markup](https://rich.readthedocs.io/en/stable/markup.html). `self.stdout`, `self.stderr` and `self.style` still work but are deprecated: they raise `heavy_water.HeavyWaterDeprecationWarning` (a `FutureWarning`) when used, and the `heavy_water.W001` system check reports builders whose source uses them.
- **`get_or_create_superuser()` refuses the default `rootroot` password when `DEBUG` is `False`**, raising `ImproperlyConfigured`. Pass `password=` or set `HEAVY_WATER_SUPERUSER_PASSWORD`. Existing users are still returned.
- **Builders run in the order they're defined**, not alphabetically. Use `depends_on` when one builder needs another to run first.
- **Only builders defined in a fixtures module run from it.** A builder imported into another fixtures module no longer runs twice, and abstract base classes are no longer instantiated.

### Added

- `depends_on` class attribute: builders it lists run first, even from other apps. If a dependency fails, the builder is reported as failed without running; if a dependency is skipped, so is the builder. Cycles and undiscovered dependencies stop the command before anything runs.
- `--list`: print the builders as a tree, in run order, with their dependencies. Builders that would be skipped are dimmed.
- `--dry-run`: run the builders, then roll back their database changes. Can't be combined with `--wipe`.
- `--only` and `--exclude`, taking `app_label` or `app_label.BuilderName`. `--only` also runs dependencies; `--exclude` also drops dependents.
- Rich tracebacks for failing builders.
- `heavy_water.W001` system check for the deprecated output attributes.
- New dependency: [django-rich](https://github.com/adamchainz/django-rich).

## 0.2.1 - 2026-09-23

### Upgrading from 0.2.0

- **Requires Django 4.2 or later** (previously 3.0).
- **Environments are replaced by `should_run()`.** `DJANGO_ENV`, `HEAVY_WATER_ENV_MAPPING` and the `DEV` / `TEST` / `STAGING` / `PROD` class attributes are gone. Override `should_run(self, *args, **options)` to decide when a builder runs; it receives the command's arguments and options. **It returns `True` by default, so every builder now runs in every environment**, including production, unless you override it, for example with `return settings.DEBUG`.
- **`heavy_water.settings` is now `heavy_water.conf`.** Read settings through `heavy_water.conf.app_settings`. Settings are read when used, so `override_settings` works.
- **`HEAVY_WATER_CREATE_ROOT_USER` is removed.** It never did anything.
- **Builder failures are exceptions.** `_heavy_water()` returns `True` if the builder ran and `False` if it was skipped. The command still reports each failure and continues with the other builders.
- Output lines now read `app - Builder: message`, and the failure summary lists builders the same way.

### Added

- `--database` is honored: the command's transaction, each builder's savepoint and `get_or_create_superuser()` use it, and builders get it as `self.database` for their own queries (`.using(self.database)`). The new `HEAVY_WATER_DATABASE` setting sets the default.
- `get_or_create_superuser()` supports custom user models, including ones that log in by email, and sets first and last names on models that have them.
- `builder_name` property on builders.
- The package ships type information (`py.typed`).

### Fixed

- `get_or_create_superuser()` no longer ignores `first_name` and `last_name`, and only saves the user a second time when `configure_user` is given.

## 0.2.0

Baseline for this changelog.
