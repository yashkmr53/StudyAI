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


def set_profile_context(profile_id, *, local: bool = True) -> None:
    """Bind the profile RLS context to the current transaction (or session if local=False)."""
    if connection.vendor != "postgresql":
        return  # RLS is PostgreSQL-only; unit tests on SQLite skip binding.
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, %s)", [RLS_GUC, str(profile_id) if profile_id else "", local])


def bind_profile_session(profile_id) -> None:
    """Bind profile RLS context at session level (useful across autocommit statements / threads)."""
    set_profile_context(profile_id, local=False)


def get_current_profile_id() -> str:
    """Read the current profile RLS setting."""
    if connection.vendor != "postgresql":
        return ""
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [RLS_GUC])
        row = cursor.fetchone()
        return row[0] if (row and row[0]) else ""


@contextmanager
def profile_scoped_transaction(profile_id):
    """Open a transaction with the RLS context bound for its whole lifetime."""
    prev = get_current_profile_id()
    with transaction.atomic():
        set_profile_context(profile_id)
        try:
            yield
        finally:
            if prev:
                set_profile_context(prev)
            else:
                clear_profile_context()


def clear_profile_context() -> None:
    """Resets RLS GUC to empty string / session default."""
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(f"RESET {RLS_GUC}")
