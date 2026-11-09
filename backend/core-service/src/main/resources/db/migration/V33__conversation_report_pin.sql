-- P25 daily report conversation (#392). Both columns stay NULL for ordinary conversations, so no column default
-- or backfill split is needed. A pinned conversation stores the report ID and revision together on one target day.
ALTER TABLE conversation
    ADD COLUMN report_id uuid,
    ADD COLUMN report_revision int,
    ADD CONSTRAINT ck_conversation_report_pair CHECK ((report_id IS NULL) = (report_revision IS NULL)),
    ADD CONSTRAINT ck_conversation_report_revision CHECK (report_revision IS NULL OR report_revision >= 1),
    ADD CONSTRAINT ck_conversation_report_day CHECK (report_id IS NULL OR period_from = period_to);
