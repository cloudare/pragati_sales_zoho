"""merge dispatch_package and po_line_item heads

Revision ID: 68282136eb45
Revises: 9032bf7869b3, c3d4e5f6a7b8
Create Date: 2026-06-30 00:37:24.431474

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68282136eb45'
down_revision: Union[str, None] = ('9032bf7869b3', 'c3d4e5f6a7b8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
