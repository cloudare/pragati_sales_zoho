"""add zoho package fields to dispatch_orders

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('dispatch_orders', sa.Column('zoho_package_id', sa.String(64), nullable=True))
    op.add_column('dispatch_orders', sa.Column('packed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('dispatch_orders', 'packed_at')
    op.drop_column('dispatch_orders', 'zoho_package_id')