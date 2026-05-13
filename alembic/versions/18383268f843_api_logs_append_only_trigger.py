"""api_logs append only trigger

Revision ID: 18383268f843
Revises: 829d815720a8
Create Date: 2026-05-12 05:00:35.302511

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18383268f843'
down_revision: Union[str, Sequence[str], None] = '829d815720a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_api_log_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'api_logs is append-only and cannot be modified or deleted';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER api_logs_immutable
        BEFORE UPDATE OR DELETE ON api_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_api_log_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS api_logs_immutable ON api_logs;")
    op.execute("DROP FUNCTION IF EXISTS prevent_api_log_mutation();")
