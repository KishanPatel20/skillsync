from django.apps import AppConfig


class Beta1Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "beta_1"

    def ready(self):
        # Import models here to avoid circular imports
        from . import models  # noqa
        try:
            import beta_1.signals  # Import signals if you have any
        except ImportError:
            pass
