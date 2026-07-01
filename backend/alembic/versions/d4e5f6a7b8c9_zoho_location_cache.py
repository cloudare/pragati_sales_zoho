"""add zoho_location_cache

Revision ID: d4e5f6a7b8c9
Revises: 68282136eb45
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = '68282136eb45'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'zoho_location_cache',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('zoho_location_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(256), nullable=False),
        sa.Column('type', sa.String(32)),
        sa.Column('gstin', sa.String(32)),
        sa.Column('address', sa.String(512)),
        sa.Column('is_primary', sa.Boolean(), server_default=sa.false()),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true()),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_zoho_location_cache_zoho_location_id', 'zoho_location_cache',
                    ['zoho_location_id'], unique=True)
    op.create_index('ix_zoho_location_cache_name', 'zoho_location_cache', ['name'])


def downgrade():
    op.drop_index('ix_zoho_location_cache_name', table_name='zoho_location_cache')
    op.drop_index('ix_zoho_location_cache_zoho_location_id', table_name='zoho_location_cache')
    op.drop_table('zoho_location_cache')