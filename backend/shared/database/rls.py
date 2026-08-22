"""Transaction-local RLS context (architecture §3).

RLS policies read `app.current_profile_id`. The setting is applied with
SET LOCAL so it lives only inside the current transaction — required when
using pooled connections. Celery workers must call these helpers explicitly
after loading a trusted job payload; they never accept client-supplied
profile IDs.
"""
from contextlib import contextmanager

from django.db import connection, transaction

RLS_GUC = "app.current_profile_id"


def set_profile_context(profile_id) -> None:
    """Bind the profile RLS context to the *current transaction* (SET LOCAL)."""
    if connection.vendor != "postgresql":
        return  # RLS is PostgreSQL-only; unit tests on SQLite skip binding.
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, true)", [RLS_GUC, str(profile_id)])


@contextmanager
def profile_scoped_transaction(profile_id):
    """Open a transaction with the RLS context bound for its whole lifetime."""
    with transaction.atomic():
        set_profile_context(profile_id)
        yield


def clear_profile_context() -> None:
    """No-op outside a transaction; inside one, resets to session default."""
    with connection.cursor() as cursor:
        cursor.execute(f"RESET {RLS_GUC}")
