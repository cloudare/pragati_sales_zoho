"""add_purchase_receive_id

Revision ID: 4661e2ea554f
Revises: 0c37be3581cf
Create Date: 2026-06-24 00:29:56.217157
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "4661e2ea554f"
down_revision: Union[str, None] = "0c37be3581cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "grns",
        sa.Column(
            "zoho_purchase_receive_id",
            sa.String(length=64),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "grns",
        "zoho_purchase_receive_id",
    )