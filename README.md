# django-heavy-water

A reusable Django app that seeds your database with development and test data. Each app in your project defines *data builders*, and a single management command, `heavy_water`, runs the ones that apply to the current environment.

Requires Python 3.10+ and Django 4.2+.

## Installation

The package isn't on PyPI yet, so install it from GitHub:

```sh
pip install git+https://github.com/joshuata/django-heavy-water
```

Add it to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "heavy_water",
]
```

## Usage

### Write a data builder

Create a `fixtures.py` module in any installed app and subclass `BaseDataBuilder`:

```python
# myapp/fixtures.py
from typing import Any

from django.conf import settings

from heavy_water import BaseDataBuilder

from myapp.models import Widget


class WidgetData(BaseDataBuilder):
    def should_run(self, *args: Any, **options: Any) -> bool:
        return settings.DEBUG

    def handle(self) -> None:
        self.get_or_create_superuser()
        Widget.objects.get_or_create(name="Sprocket")
```

### Run it

```sh
python manage.py heavy_water          # run all builders
python manage.py heavy_water --wipe   # flush the database first
python manage.py heavy_water --database other   # seed a different database
python manage.py heavy_water --list   # show what would run, without running it
python manage.py heavy_water --dry-run   # run everything, then roll it back
python manage.py heavy_water --only orders.OrderData   # run one builder (plus its dependencies)
python manage.py heavy_water --exclude orders   # skip every builder in an app
```

`--list` prints the builders as a tree in the order they would run, with each builder's dependencies under it. Builders that would be skipped are dimmed and marked "(skipped)". It calls each builder's `should_run()` (with the other options you pass, such as `--wipe`) but never runs `handle()` or flushes the database:

```
Data builders, in run order
├── 1. customers - CustomerData
├── 2. orders - OrderData
│   └── depends on 1. customers - CustomerData
└── 3. orders - DemoData (skipped)
```

`--dry-run` runs every builder, `handle()` included, then rolls back all their database changes, so you can check that they work without keeping the data. Failures are still reported. Anything a builder does outside the database, such as writing files or calling an API, isn't undone. It can't be combined with `--wipe`.

`--only` and `--exclude` take an app label (`orders`) or an app label and builder class name (`orders.OrderData`), and can be repeated. `--only` also runs the selected builders' dependencies, and `--exclude` also drops builders that depend on an excluded one. `--exclude` applies after `--only`. Both work with `--list` and `--dry-run`.

`--wipe` uses Django's `flush` command, so it accepts `flush`'s options too, such as `--no-input`.

With `--database` (or the `HEAVY_WATER_DATABASE` setting), the command's transaction and `get_or_create_superuser()` use that database, and the alias is available to builders as `self.database`. Queries you write in `handle()` need to use it explicitly:

```python
Widget.objects.using(self.database).get_or_create(name="Sprocket")
```

### How builders run

- The command runs every builder it finds whose `should_run()` returns `True`. By default it always does; override it to limit a builder to certain environments, as in the example above. `should_run()` receives the command's arguments and parsed options (such as `wipe` and `verbosity`), so you can use them as conditions too, for example `return options["wipe"]`.
- Builders run in the order they're defined in each module. Apps are processed in `INSTALLED_APPS` order, and modules in `HEAVY_WATER_FIXTURE_MODULE` order. Use `depends_on` (below) when a builder needs another one to run first.
- All builders run in one transaction, and each builder gets its own savepoint. If a builder raises, only its changes are rolled back and the other builders still run.
- If any builder failed, the command exits with an error listing them after committing the rest.

### Output

The command prints with [Rich](https://rich.readthedocs.io/) via [django-rich](https://github.com/adamchainz/django-rich), including Rich tracebacks for failing builders. Colour follows Django's `--no-color` and `--force-color` flags. Inside a builder, print with `self.console` (stdout) and `self.err_console` (stderr), which accept Rich markup:

```python
self.console.print(f"Created [bold]{count}[/] widgets")
```

`self.stdout`, `self.stderr` and `self.style` still work but are deprecated, and raise `heavy_water.HeavyWaterDeprecationWarning` (a `FutureWarning`, which Python shows by default) when used. heavy_water also adds a system check, so you find out before running anything: `manage.py check` (and most other commands) reports `heavy_water.W001` for each builder whose source uses them. Use `self.console`, `self.err_console` and Rich markup instead.

To silence the check, add `"heavy_water.W001"` to `SILENCED_SYSTEM_CHECKS`.

### Dependencies between builders

List the builders a builder relies on in `depends_on`. They run before it, even if they're defined later or in another app:

```python
from otherapp.fixtures import CustomerData


class OrderData(BaseDataBuilder):
    depends_on = (CustomerData,)

    def handle(self) -> None: ...
```

- If a dependency fails, the builder doesn't run and is reported as failed too.
- If a dependency is skipped by its `should_run()`, the builder is skipped too.
- Each dependency must be a builder the command discovers. A missing dependency or a dependency cycle stops the command before anything runs, including `--wipe`.

Importing a builder into your fixtures module doesn't make it run twice: builders only run from the module that defines them.

### Creating a superuser

`get_or_create_superuser()` returns the superuser identified by the user model's `USERNAME_FIELD`, creating it if it doesn't exist. Any argument you leave out falls back to the `HEAVY_WATER_SUPERUSER_*` settings below. Custom user models are supported, including ones that log in by email.

Pass `configure_user` to adjust the user after it's fetched or created; the user is saved afterwards:

```python
self.get_or_create_superuser(
    username="admin",
    configure_user=lambda user: setattr(user, "is_active", True),
)
```

> **Note:** the default password is `rootroot`, and it's only allowed when `DEBUG = True`. With `DEBUG = False`, creating a superuser raises `ImproperlyConfigured` unless you pass `password=` or set `HEAVY_WATER_SUPERUSER_PASSWORD`. Existing users are still returned as normal.

## Settings

All settings are optional.

| Setting | Default | Description |
| --- | --- | --- |
| `HEAVY_WATER_FIXTURE_MODULE` | `["fixtures"]` | Submodule names searched for builders in each installed app. |
| `HEAVY_WATER_DATABASE` | `"default"` | Alias from `DATABASES` to seed. `--database` overrides it. |
| `HEAVY_WATER_SUPERUSER_USERNAME` | `"root"` | Default login for `get_or_create_superuser()` (the email is used instead when the login field is the email). |
| `HEAVY_WATER_SUPERUSER_EMAIL` | `"root@example.com"` | Default email. |
| `HEAVY_WATER_SUPERUSER_PASSWORD` | `"rootroot"` | Default password. |
| `HEAVY_WATER_SUPERUSER_FIRST_NAME` | `"Root"` | Default first name, if the user model has the field. |
| `HEAVY_WATER_SUPERUSER_LAST_NAME` | `"User"` | Default last name, if the user model has the field. |

## Development

Development tooling is managed by [mise](https://mise.jdx.dev). It installs [uv](https://docs.astral.sh/uv/) and [hk](https://hk.jdx.dev), and activates the project's `.venv`. uv installs the Python dev tools, including [ruff](https://docs.astral.sh/ruff/), into `.venv`. Every development script is a mise task, so run everything through `mise run`.

First-time setup:

```sh
mise install     # install uv and hk, and the pre-commit hook
```

That's all: the first `mise run` or `mise x` creates `.venv` with `uv sync`, and mise re-syncs it automatically whenever `pyproject.toml` or `uv.lock` changes (via [`mise deps`](https://mise.jdx.dev/dev-tools/deps.html), an experimental mise feature this project enables). `mise run setup` does both steps explicitly.

Tasks:

| Command | What it does |
| --- | --- |
| `mise run setup` | Runs `sync` and `hooks`. |
| `mise run sync` | Installs the package and dev dependencies into `.venv`. |
| `mise run hooks` | Installs the hk pre-commit hook. |
| `mise run lint` | Syncs `.venv`, then runs all checks: ruff lint, ruff format, mypy and `uv lock --check`. The pre-commit hook runs the same checks. |
| `mise run fix` | Applies ruff fixes and formatting, and updates `uv.lock`. |
| `mise run test` | Runs the test suite with pytest. |
| `DJANGO=5.2 mise run test-django` | Runs the tests against another Django version. Set `UV_PYTHON` to pick the Python version too. |
| `mise run demo [options]` | Runs `heavy_water` against the test app, so you can see its output. Options are passed to the command, e.g. `mise run demo --list`. `DEMO_MODULES` picks the test builder modules. |
| `mise run typecheck` | Runs mypy in strict mode on the package. |
| `mise run build` | Builds the sdist and wheel into `dist/`. |
| `mise run bump [major\|minor\|patch]` | Bumps the version (patch by default), commits `pyproject.toml` and `uv.lock`, and tags the commit, e.g. `v0.2.1`. |
| `mise run publish` | Uploads `dist/` to PyPI. Normally run by the publish workflow, not by hand. |

Run `mise tasks` to list them. To add a script, define it as a task in `mise.toml`.

### CI and releases

GitHub Actions (`.github/workflows/`) runs everything through the same mise tasks:

- **CI** (`ci.yml`), on pushes to `main` and on pull requests: `lint` and `build`, then `test-django` across supported Python and Django versions.
- **Publish** (`publish.yml`), when a GitHub release is published: checks the release tag matches the version in `pyproject.toml` (`v0.3.0` or `0.3.0` for version `0.3.0`), runs lint, tests and build, then uploads to PyPI with trusted publishing.

To release, run `mise run bump` (or `bump minor` / `bump major`), push with `git push --follow-tags`, and publish a GitHub release from the new tag.

The package ships a `py.typed` marker and is checked with mypy in strict mode, so new code must be fully type-annotated.

## License

BSD 3-Clause. See [LICENSE](LICENSE).
