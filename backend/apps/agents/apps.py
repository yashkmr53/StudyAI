from django.apps import AppConfig


class AgentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.agents"
    verbose_name = "StudyAI Agents"

    def ready(self):
        # Import tools to register them
        from apps.agents.tools import retrieval, learning, evidence, document  # noqa: F401
        # Import prompts to seed
        from apps.agents.prompts import agent_prompts  # noqa: F401