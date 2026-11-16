-- P24 daily report (#390), preparation step. Add the period type as nullable without a column default
-- (scripts/verify_db_schema.py forbids defaults). V30 fills existing rows and applies NOT NULL/CHECK.
ALTER TABLE report_job ADD COLUMN period_type varchar;
