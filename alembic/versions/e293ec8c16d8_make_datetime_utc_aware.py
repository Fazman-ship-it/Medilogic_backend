"""make datetime utc aware

Revision ID: e293ec8c16d8
Revises: 76ec968f36e1
Create Date: 2025-10-02 14:15:04.764021

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e293ec8c16d8'
down_revision: Union[str, Sequence[str], None] = '76ec968f36e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass