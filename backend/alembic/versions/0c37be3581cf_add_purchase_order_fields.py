"""add_purchase_order_fields

Revision ID: 0c37be3581cf
Revises: b2c3d4e5f6a7
Create Date: 2026-06-24 00:08:14.200212
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0c37be3581cf"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "gate_entries",
        sa.Column("zoho_purchase_order_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "gate_entries",
        sa.Column("purchase_order_number", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "grns",
        sa.Column("zoho_purchase_order_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "grns",
        sa.Column("purchase_order_number", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("grns", "purchase_order_number")
    op.drop_column("grns", "zoho_purchase_order_id")
    op.drop_column("gate_entries", "purchase_order_number")
    op.drop_column("gate_entries", "zoho_purchase_order_id")