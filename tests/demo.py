"""Run the heavy_water command against the test app, to see its output.

Arguments are passed to the command, and ``DEMO_MODULES`` picks the test app's
builder modules (comma-separated)::

    mise run demo
    mise run demo --list
    DEMO_MODULES=fixtures_deprecated mise run demo
"""

import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")

import django  # noqa: E402
from django.conf import settings  # noqa: E402
from django.core.management import call_command, execute_from_command_line  # noqa: E402

DEFAULT_MODULES = "fixtures,fixtures_mixed,fixtures_depends"


def main() -> None:
    django.setup()
    settings.HEAVY_WATER_FIXTURE_MODULE = os.environ.get(
        "DEMO_MODULES", DEFAULT_MODULES
    ).split(",")
    # Allow get_or_create_superuser()'s default password.
    settings.DEBUG = True
    # The database is in memory, so create the tables in this process.
    call_command("migrate", run_syncdb=True, verbosity=0)
    execute_from_command_line(["manage.py", "heavy_water", *sys.argv[1:]])


if __name__ == "__main__":
    main()
