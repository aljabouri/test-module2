"""Operational columns: scans.organization_id (worker/expert org context under
RLS) and processed_stripe_events (EDGE-BIL-02 webhook idempotency)."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


SYSTEM_BYPASS_TABLES = ["users", "subscriptions"]
# Narrow, named system bypass for flows that legitimately run WITHOUT an org
# context: login lookup by email, Stripe webhook lookup by customer id.
# `properties` deliberately keeps the strict policy — no bypass exists for it.


def upgrade() -> None:
    # 0001 is create_all-based (tracks the CURRENT models), so additions here
    # must be idempotent for fresh installs while still upgrading old DBs.
    op.execute("ALTER TABLE scans ADD COLUMN IF NOT EXISTS organization_id UUID")
    op.execute("""
        CREATE TABLE IF NOT EXISTS processed_stripe_events (
            event_id TEXT PRIMARY KEY,
            processed_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in SYSTEM_BYPASS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS org_isolation_{table} ON {table};")
        op.execute(f"""
            CREATE POLICY org_isolation_{table} ON {table}
            USING (
              organization_id = NULLIF(current_setting('app.current_org', true), '')::uuid
              OR current_setting('app.rls_bypass', true) = 'system'
            )
            WITH CHECK (
              organization_id = NULLIF(current_setting('app.current_org', true), '')::uuid
              OR current_setting('app.rls_bypass', true) = 'system'
            );
        """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in SYSTEM_BYPASS_TABLES:
            op.execute(f"DROP POLICY IF EXISTS org_isolation_{table} ON {table};")
            op.execute(f"""
                CREATE POLICY org_isolation_{table} ON {table}
                USING (organization_id = NULLIF(current_setting('app.current_org', true), '')::uuid)
                WITH CHECK (organization_id = NULLIF(current_setting('app.current_org', true), '')::uuid);
            """)
    op.drop_table("processed_stripe_events")
    op.drop_column("scans", "organization_id")
