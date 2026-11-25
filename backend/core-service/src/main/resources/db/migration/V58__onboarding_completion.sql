-- #1035 첫 사용 안내 완료 시각. NULL = 아직 안 봄. 처음 기록한 시각을 유지하고 지우는 API는 없다.
-- 학생은 user_account 행이 없어(V7) student에 둔다(look_updated_at 선례).
ALTER TABLE user_account ADD COLUMN onboarding_completed_at timestamptz;
ALTER TABLE student ADD COLUMN onboarding_completed_at timestamptz;
