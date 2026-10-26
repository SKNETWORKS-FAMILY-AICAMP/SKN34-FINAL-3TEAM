-- Finalize P01/P02/P03/P10/P13 after the additive V6 preparation.
-- Each Flyway migration is transactional. Failed checks leave V6 available
-- for reviewed backfill; they do not delete rows or fabricate policy values.

LOCK TABLE student, product, guardianship, notification_setting, error_report
    IN ACCESS EXCLUSIVE MODE;

DO $policy_preflight$
BEGIN
    IF EXISTS (SELECT 1 FROM student WHERE birth_year IS NULL) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'P01: backfill student.birth_year from verified registration data before V7';
    END IF;
    IF EXISTS (SELECT 1 FROM student WHERE user_account_id IS NOT NULL) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'P01: review and preserve existing student account links before clearing user_account_id and applying V7';
    END IF;
    IF EXISTS (SELECT 1 FROM student WHERE grade NOT BETWEEN 3 AND 6) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'P03: existing student grades outside 3..6 need an explicit transition decision before V7';
    END IF;
    IF EXISTS (SELECT 1 FROM product WHERE price IS NULL OR limits IS NULL) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'P13: backfill product.price and product.limits from approved product terms before V7';
    END IF;
    IF EXISTS (SELECT 1 FROM guardianship WHERE method <> 'REGISTER') THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'P02: existing LINK guardianships need an explicit transition decision before V7';
    END IF;
    IF EXISTS (SELECT 1 FROM notification_setting WHERE channel <> 'IN_APP') THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'P10: preserve or explicitly retire non-IN_APP notification preferences before V7';
    END IF;
    IF EXISTS (
        SELECT 1 FROM error_report WHERE category IS NULL OR category NOT IN (
            'WRONG_JUDGMENT', 'ODD_QUESTION', 'MISMATCH', 'INAPPROPRIATE', 'OTHER'
        )
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'P10: classify existing error_report.category into the five approved categories before V7';
    END IF;
END;
$policy_preflight$;

ALTER TABLE student
    DROP COLUMN user_account_id,
    ALTER COLUMN birth_year SET NOT NULL,
    ADD CONSTRAINT ck_student_grade CHECK (grade BETWEEN 3 AND 6);

ALTER TABLE product
    ALTER COLUMN price SET NOT NULL,
    ALTER COLUMN limits SET NOT NULL;

ALTER TABLE guardianship
    DROP CONSTRAINT ck_guardianship_method,
    ADD CONSTRAINT ck_guardianship_method CHECK (method IN ('REGISTER'));

ALTER TABLE notification_setting
    DROP CONSTRAINT ck_notification_setting_channel,
    ADD CONSTRAINT ck_notification_setting_channel CHECK (channel IN ('IN_APP'));

ALTER TABLE error_report
    ALTER COLUMN category SET NOT NULL,
    ADD CONSTRAINT ck_error_report_category CHECK (category IN (
        'WRONG_JUDGMENT', 'ODD_QUESTION', 'MISMATCH', 'INAPPROPRIATE', 'OTHER'
    ));
