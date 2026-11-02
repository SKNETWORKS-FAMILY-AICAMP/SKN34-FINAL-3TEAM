"""Keep a student deletion barrier so late generation commands cannot recreate reports.

Revision ID: 20261027_02
Revises: 20261026_01
"""

from alembic import op

revision = "20261027_02"
down_revision = "20261026_01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE report_deletion_guard (
            student_id uuid PRIMARY KEY,
            scope varchar NOT NULL CHECK (scope IN ('PROFILE', 'RECORDS')),
            cutoff_at timestamptz NOT NULL,
            deletion_request_id uuid NOT NULL,
            status varchar NOT NULL CHECK (status IN ('PENDING', 'COMPLETED')),
            updated_at timestamptz NOT NULL
        )
    """)


def downgrade():
    op.drop_table("report_deletion_guard")
