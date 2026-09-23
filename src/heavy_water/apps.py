from django.apps import AppConfig


class HeavyWaterConfig(AppConfig):
    name = "heavy_water"
    default_auto_field = "django.db.models.AutoField"

    def ready(self) -> None:
        from heavy_water import checks  # noqa: F401  (registers the checks)
