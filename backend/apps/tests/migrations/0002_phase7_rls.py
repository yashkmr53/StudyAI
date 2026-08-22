"""RLS on Phase 7 learning-feature tables (architecture §3).

Direct profile scoping: tests/attempts/mastery/chat/revision goals.
Tag tables scope through subject → profile EXISTS chains. No-op on SQLite.
"""
from django.db import migrations

POLICIES = [
    # tags scope via their subject's profile
    (
        "ai_classroom_tag",
        "profile_isolation_tag",
        "USING (EXISTS (SELECT 1 FROM subjects_subject s WHERE s.id = subject_id "
        "AND s.profile_id::text = current_setting('app.current_profile_id', true)));",
    ),
    (
        "ai_classroom_documenttag",
        "profile_isolation_documenttag",
        "USING (EXISTS (SELECT 1 FROM documents_document d WHERE d.id = document_id "
        "AND d.profile_id::text = current_setting('app.current_profile_id', true)));",
    ),
    (
        "ai_classroom_tagchangelog",
        "profile_isolation_tagchangelog",
        "USING (EXISTS (SELECT 1 FROM ai_classroom_tag t WHERE t.id = tag_id "
        "AND EXISTS (SELECT 1 FROM subjects_subject s WHERE s.id = t.subject_id "
        "AND s.profile_id::text = current_setting('app.current_profile_id', true))));",
    ),
    (
        "questions_question",
        "profile_isolation_question",
        "USING (EXISTS (SELECT 1 FROM documents_document d WHERE d.id = document_id "
        "AND d.profile_id::text = current_setting('app.current_profile_id', true)));",
    ),
    (
        "tests_testinstance",
        "profile_isolation_test",
        "USING (profile_id::text = current_setting('app.current_profile_id', true));",
    ),
    (
        "tests_testattempt",
        "profile_isolation_testattempt",
        "USING (EXISTS (SELECT 1 FROM tests_testinstance ti WHERE ti.id = test_id "
        "AND ti.profile_id::text = current_setting('app.current_profile_id', true)));",
    ),
    (
        "tests_masteryscore",
        "profile_isolation_mastery",
        "USING (profile_id::text = current_setting('app.current_profile_id', true));",
    ),
    (
        "chat_chatsession",
        "profile_isolation_chatsession",
        "USING (profile_id::text = current_setting('app.current_profile_id', true));",
    ),
    (
        "chat_chatmessage",
        "profile_isolation_chatmessage",
        "USING (EXISTS (SELECT 1 FROM chat_chatsession cs WHERE cs.id = session_id "
        "AND cs.profile_id::text = current_setting('app.current_profile_id', true)));",
    ),
    (
        "revision_revisiongoal",
        "profile_isolation_revisiongoal",
        "USING (profile_id::text = current_setting('app.current_profile_id', true));",
    ),
]


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table, policy_name, using in POLICIES:
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
            cursor.execute(f"CREATE POLICY {policy_name} ON \"{table}\" {using}")


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table, policy_name, _ in POLICIES:
            cursor.execute(f'DROP POLICY IF EXISTS {policy_name} ON "{table}";')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [
        ("tests", "0001_initial"),
        ("chat", "0001_initial"),
        ("revision", "0001_initial"),
        ("questions", "0001_initial"),
        ("ai_classroom", "0002_enable_rls"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
