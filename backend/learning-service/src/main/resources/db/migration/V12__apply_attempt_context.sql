-- #385 시도 컨텍스트 최종 (P23, ERD 4.2): V11에서 채운 context를 NOT NULL·CHECK로 확정한다.
-- 테마 컨텍스트(THEME_DAY·THEME_REVIEW)는 그 주 테마와 주 시작일이 함께 있고, EXTRA는 둘 다 비운다.

LOCK TABLE attempt IN ACCESS EXCLUSIVE MODE;

DO $context_preflight$
BEGIN
    IF EXISTS (SELECT 1 FROM attempt WHERE context IS NULL) THEN
        RAISE EXCEPTION USING ERRCODE = '23502',
            MESSAGE = 'P23: fill attempt.context for every existing attempt before V12';
    END IF;
    IF EXISTS (
        SELECT 1 FROM attempt
        WHERE context NOT IN ('THEME_DAY', 'THEME_REVIEW', 'EXTRA')
           OR (context = 'EXTRA' AND (theme_id IS NOT NULL OR theme_week_start IS NOT NULL))
           OR (context <> 'EXTRA' AND (theme_id IS NULL OR theme_week_start IS NULL))
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'P23: resolve attempt.context and theme columns explicitly before V12';
    END IF;
END;
$context_preflight$;

ALTER TABLE attempt ALTER COLUMN context SET NOT NULL;

ALTER TABLE attempt
    ADD CONSTRAINT ck_attempt_context
        CHECK (context IN ('THEME_DAY', 'THEME_REVIEW', 'EXTRA')),
    ADD CONSTRAINT ck_attempt_theme_context CHECK (
        (context = 'EXTRA' AND theme_id IS NULL AND theme_week_start IS NULL)
        OR (context <> 'EXTRA' AND theme_id IS NOT NULL AND theme_week_start IS NOT NULL)
    );
