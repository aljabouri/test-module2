"""Admin control plane (ISO/CM): client_profiles + client_notes +
hash-chained admin_audit_log, organizations.suspended kill-switch, and the
named SELECT-only `admin_ro` RLS bypass so the control plane can read across
organizations WITHOUT gaining write access to customer tables.

IF NOT EXISTS throughout — 0001 is create_all-based."""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

RLS_TABLES = ["properties", "users", "subscriptions"]

STATEMENTS = [
    "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS suspended BOOLEAN NOT NULL DEFAULT false",
    """
    CREATE TABLE IF NOT EXISTS client_profiles (
        id UUID PRIMARY KEY,
        organization_id UUID NOT NULL UNIQUE,
        lifecycle TEXT NOT NULL DEFAULT 'onboarding',
        lifecycle_pinned BOOLEAN NOT NULL DEFAULT false,
        account_owner TEXT,
        tags TEXT[],
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS client_notes (
        id UUID PRIMARY KEY,
        organization_id UUID NOT NULL,
        author_user_id UUID NOT NULL,
        kind TEXT NOT NULL DEFAULT 'note',
        body TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS admin_audit_log (
        id UUID PRIMARY KEY,
        sequence_number INTEGER NOT NULL UNIQUE,
        actor_user_id UUID NOT NULL,
        action TEXT NOT NULL,
        target_type TEXT,
        target_id TEXT,
        payload JSONB,
        content_hash TEXT NOT NULL,
        prev_hash TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now()
    )
    """,
]

PG_STATEMENTS = [
    # Append-only: notes and audit entries are evidence, not documents.
    """
    CREATE OR REPLACE FUNCTION konformos_forbid_admin_log_mutation()
    RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION 'ISO-04: % is append-only (no % allowed)', TG_TABLE_NAME, TG_OP;
    END;
    $$ LANGUAGE plpgsql;
    """,
    "DROP TRIGGER IF EXISTS client_notes_append_only ON client_notes;",
    """
    CREATE TRIGGER client_notes_append_only
    BEFORE UPDATE OR DELETE ON client_notes
    FOR EACH ROW EXECUTE FUNCTION konformos_forbid_admin_log_mutation();
    """,
    "DROP TRIGGER IF EXISTS admin_audit_append_only ON admin_audit_log;",
    """
    CREATE TRIGGER admin_audit_append_only
    BEFORE UPDATE OR DELETE ON admin_audit_log
    FOR EACH ROW EXECUTE FUNCTION konformos_forbid_admin_log_mutation();
    """,
] + [
    # ISO-02: named READ-ONLY cross-org bypass. Additive (permissive policies
    # OR together) — customer traffic is untouched; only sessions that set
    # app.rls_bypass = 'admin_ro' gain SELECT, and nothing but SELECT.
    stmt
    for table in RLS_TABLES
    for stmt in (
        f"DROP POLICY IF EXISTS admin_ro_read_{table} ON {table};",
        f"""
        CREATE POLICY admin_ro_read_{table} ON {table} FOR SELECT
        USING (current_setting('app.rls_bypass', true) = 'admin_ro');
        """,
    )
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    if op.get_bind().dialect.name != "postgresql":
        return
    for statement in PG_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in RLS_TABLES:
            op.execute(f"DROP POLICY IF EXISTS admin_ro_read_{table} ON {table};")
        op.execute("DROP TRIGGER IF EXISTS admin_audit_append_only ON admin_audit_log;")
        op.execute("DROP TRIGGER IF EXISTS client_notes_append_only ON client_notes;")
        op.execute("DROP FUNCTION IF EXISTS konformos_forbid_admin_log_mutation();")
    op.drop_table("admin_audit_log")
    op.drop_table("client_notes")
    op.drop_table("client_profiles")
    op.drop_column("organizations", "suspended")
