"""PostgreSQL hardening: append-only timeline trigger (INV-TL-01),
one-active-pack partial index (INV-RP-02), Row-Level Security (INV-ORG-01)."""
from alembic import op

from konformos.db.hardening import HARDENING_DROP_STATEMENTS, HARDENING_STATEMENTS

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for statement in HARDENING_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for statement in HARDENING_DROP_STATEMENTS:
        op.execute(statement)
