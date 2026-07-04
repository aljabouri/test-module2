"""Initial schema — all 19 tables from Tech Spec v1.0 §6.

Reminder (Rules-as-Data): rule/pack CONTENT updates are rows, never
migrations. This file only changes when the STRUCTURE changes.
"""
from alembic import op

from konformos.db.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
