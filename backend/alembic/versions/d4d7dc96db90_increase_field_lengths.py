"""increase_field_lengths

Revision ID: d4d7dc96db90
Revises: 4661e2ea554f
Create Date: 2026-06-25 13:11:50.771252
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "d4d7dc96db90"
down_revision: Union[str, None] = "4661e2ea554f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "zoho_item_cache",
        "sku",
        existing_type=sa.VARCHAR(length=64),
        type_=sa.String(length=100),
        existing_nullable=True,
    )

    op.alter_column(
        "zoho_item_cache",
        "unit",
        existing_type=sa.VARCHAR(length=16),
        type_=sa.String(length=100),
        existing_nullable=True,
    )

    op.alter_column(
        "zoho_item_cache",
        "brand",
        existing_type=sa.VARCHAR(length=64),
        type_=sa.String(length=100),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "zoho_item_cache",
        "brand",
        existing_type=sa.String(length=100),
        type_=sa.VARCHAR(length=64),
        existing_nullable=True,
    )

    op.alter_column(
        "zoho_item_cache",
        "unit",
        existing_type=sa.String(length=100),
        type_=sa.VARCHAR(length=16),
        existing_nullable=True,
    )

    op.alter_column(
        "zoho_item_cache",
        "sku",
        existing_type=sa.String(length=100),
        type_=sa.VARCHAR(length=64),
        existing_nullable=True,
    )