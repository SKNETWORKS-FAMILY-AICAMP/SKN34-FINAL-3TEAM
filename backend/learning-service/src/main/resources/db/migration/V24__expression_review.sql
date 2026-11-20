-- #727 표현 검토 대기 (에픽 #688 재학습 자동화, 설계 #725, docs/design/erd.md 4.3.2).
-- 이미 저장된 답변만 가리키고 원문은 복사하지 않는다. 막힌 답변(저장 안 됨)·모델 점수는 저장하지 않는다(NFR-SEC-05).
-- 새 테이블만 추가하므로 기존 행 채움 단계가 없다. 기본값은 두지 않고 앱이 모든 값을 넘긴다.
-- 학생 삭제(P09)는 cascade 대신 답변보다 먼저 같은 트랜잭션에서 지운다(FK NO ACTION, 4.3.1과 같은 방식).

CREATE TABLE expression_review (
    id uuid NOT NULL,
    answer_id uuid NOT NULL,
    source varchar NOT NULL,
    model_version varchar,
    label varchar,
    labeled_by uuid,
    labeled_at timestamptz,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_expression_review PRIMARY KEY (id),
    CONSTRAINT uq_expression_review_answer_id_source UNIQUE (answer_id, source),
    CONSTRAINT fk_expression_review_answer_id FOREIGN KEY (answer_id) REFERENCES answer (id),
    CONSTRAINT ck_expression_review_source CHECK (source IN ('GRAY_ZONE', 'COMMUNITY_REPORT')),
    CONSTRAINT ck_expression_review_label CHECK (label IN ('OFFENSIVE', 'CLEAN', 'SKIP'))
);

-- 라벨 없는 검토 목록(오래된 순)
CREATE INDEX ix_expression_review_label_created_at
    ON expression_review (label, created_at);

-- 재학습 새 라벨 수·내보내기(labeled_at 순)
CREATE INDEX ix_expression_review_labeled_at
    ON expression_review (labeled_at) WHERE label IS NOT NULL;
