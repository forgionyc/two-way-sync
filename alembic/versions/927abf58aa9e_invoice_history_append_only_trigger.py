"""invoice_history append only trigger

Revision ID: 927abf58aa9e
Revises: 18383268f843
Create Date: 2026-05-12 05:05:03.410593

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '927abf58aa9e'
down_revision: Union[str, Sequence[str], None] = '18383268f843'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_invoice_history_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'invoice_history is append-only and cannot be modified or deleted';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER invoice_history_immutable
        BEFORE UPDATE OR DELETE ON invoice_history
        FOR EACH ROW EXECUTE FUNCTION prevent_invoice_history_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS invoice_history_immutable ON invoice_history;")
    op.execute("DROP FUNCTION IF EXISTS prevent_invoice_history_mutation();")
