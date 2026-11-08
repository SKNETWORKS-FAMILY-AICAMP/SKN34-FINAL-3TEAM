-- #388 P20 최종 버전: 기존 학생은 공개 끔으로 채우고 NOT NULL로 고정한다.
-- 신규 학생도 끈 상태로 시작하도록 기본값 false를 둔다(parent_sharing_enabled와 같은 비공개 기본값 예외, ERD 3.1).
UPDATE student SET community_enabled = false WHERE community_enabled IS NULL;
ALTER TABLE student ALTER COLUMN community_enabled SET DEFAULT false,
    ALTER COLUMN community_enabled SET NOT NULL;
