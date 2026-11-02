-- #145 공개 버전 (P07, ERD 4.1): 학생 목록·상세·시도 시작은 published_*, 관리자 편집은 current_*.
-- 게시 때 published_* <- current_* 이라 공개 중 수정본은 재검토·재게시 전까지 학생에게 보이지 않는다.

ALTER TABLE mission ADD COLUMN published_version_id uuid;
ALTER TABLE mission ADD COLUMN published_rubric_version_id uuid;

ALTER TABLE mission
    ADD CONSTRAINT fk_mission_published_version_id
    FOREIGN KEY (published_version_id) REFERENCES mission_version (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION
    DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE mission
    ADD CONSTRAINT fk_mission_published_rubric_version_id
    FOREIGN KEY (published_rubric_version_id) REFERENCES rubric_version (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION
    DEFERRABLE INITIALLY IMMEDIATE;

-- 지금 학생에게 보이는 버전(= 지금까지의 current_*)을 그대로 공개 버전으로: V7 적용 전후 학생 화면이 같음
UPDATE mission
SET published_version_id = current_version_id,
    published_rubric_version_id = current_rubric_version_id
WHERE status = 'PUBLISHED';
