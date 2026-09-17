from django.apps import AppConfig


class ResearchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "research"

    def ready(self):
        from django.db.models.signals import post_delete

        from .signals import delete_passage_scope

        post_delete.connect(
            delete_passage_scope,
            sender="research.Dossier",
            dispatch_uid="research.delete_passage_scope",
        )
