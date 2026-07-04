"""Growth features: notifications + outbound webhooks (System 10), agency
property grants (BR-CUST-04), deploy-hook tokens (Flow C), TOTP secret
(RBAC-02). IF NOT EXISTS throughout — 0001 is create_all-based."""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

STATEMENTS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_secret TEXT",
    """
    CREATE TABLE IF NOT EXISTS notifications (
        id UUID PRIMARY KEY,
        organization_id UUID NOT NULL,
        type TEXT NOT NULL,
        payload JSONB,
        channel TEXT NOT NULL DEFAULT 'email',
        status TEXT NOT NULL DEFAULT 'queued',
        created_at TIMESTAMPTZ DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS webhook_endpoints (
        id UUID PRIMARY KEY,
        organization_id UUID NOT NULL,
        url TEXT NOT NULL,
        secret TEXT NOT NULL,
        active BOOLEAN NOT NULL DEFAULT true,
        failure_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS property_grants (
        user_id UUID NOT NULL,
        property_id UUID NOT NULL,
        PRIMARY KEY (user_id, property_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS deploy_tokens (
        token TEXT PRIMARY KEY,
        property_id UUID NOT NULL,
        organization_id UUID NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now()
    )
    """,
    # INV-TL-06 refinement: timestamp_token is the ONE mutable column
    # (TSA backfill). Every sealed column stays trigger-protected.
    """
    CREATE OR REPLACE FUNCTION konformos_forbid_timeline_mutation()
    RETURNS trigger AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'INV-TL-01: timeline_events is append-only (no DELETE allowed)';
      END IF;
      IF NEW.id IS DISTINCT FROM OLD.id
         OR NEW.property_id IS DISTINCT FROM OLD.property_id
         OR NEW.sequence_number IS DISTINCT FROM OLD.sequence_number
         OR NEW.event_type IS DISTINCT FROM OLD.event_type
         OR NEW.payload IS DISTINCT FROM OLD.payload
         OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
         OR NEW.prev_hash IS DISTINCT FROM OLD.prev_hash
         OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'INV-TL-01: timeline_events sealed columns are immutable (no % allowed)', TG_OP;
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """,
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table in ("deploy_tokens", "property_grants", "webhook_endpoints", "notifications"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_secret")
