-- #484 큰 질문 정답 고르기(P23, state-diagram 3.2.2): 학생·주당 1행(한 주 한 번, ON CONFLICT DO NOTHING).
-- 금요일 문제를 마무리한 뒤 후보 중 하나를 고르고, 엔딩 상태는 저장하지 않고 이 행과 다시 풀기 기록으로 계산한다.
-- mission_id는 고를 때의 금요일 문제, correct는 고를 때 정답과 같았는지. 학생 삭제 때 물리 삭제
CREATE TABLE theme_answer_pick (
    student_id uuid NOT NULL,
    week_start date NOT NULL,
    theme_id uuid NOT NULL,
    mission_id uuid NOT NULL,
    pick varchar(100) NOT NULL,
    correct boolean NOT NULL,
    picked_at timestamptz NOT NULL,
    CONSTRAINT pk_theme_answer_pick PRIMARY KEY (student_id, week_start),
    CONSTRAINT ck_theme_answer_pick_week_start_monday CHECK (EXTRACT(ISODOW FROM week_start) = 1)
);

ALTER TABLE theme_answer_pick
    ADD CONSTRAINT fk_theme_answer_pick_theme_id
    FOREIGN KEY (theme_id) REFERENCES weekly_theme (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE theme_answer_pick
    ADD CONSTRAINT fk_theme_answer_pick_mission_id
    FOREIGN KEY (mission_id) REFERENCES mission (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;
