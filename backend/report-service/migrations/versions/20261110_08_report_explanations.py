"""Allow verified explanation items; state uses the existing verification JSONB (#479)."""

from alembic import op

revision = "20261110_08"
down_revision = "20261109_07"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE report_item DROP CONSTRAINT ck_report_item_item_type;
        ALTER TABLE report_item ADD CONSTRAINT ck_report_item_item_type CHECK
            (item_type IN ('METRIC','THINKING_TYPE','CHANGE','REFLECTION','QUOTE',
                          'PROBLEM','EXPLANATION'));
    """)


def downgrade():
    # Never delete generated explanations to make a downgrade pass.
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM report_item WHERE item_type = 'EXPLANATION')
             OR EXISTS (SELECT 1 FROM weekly_report WHERE verification ? 'explanationState') THEN
            RAISE EXCEPTION 'Explanation data exists: archive explicitly before downgrade';
          END IF;
        END $$;
        ALTER TABLE report_item DROP CONSTRAINT ck_report_item_item_type;
        ALTER TABLE report_item ADD CONSTRAINT ck_report_item_item_type CHECK
            (item_type IN ('METRIC','THINKING_TYPE','CHANGE','REFLECTION','QUOTE','PROBLEM'));
    """)
