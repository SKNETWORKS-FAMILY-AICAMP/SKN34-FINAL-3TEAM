-- #704 내 방 바닥·방 소품(P22·P27 개정, 사용자 결정 2026-11-16). V35·V47은 고치지 않고 이 버전에서 바꾼다.
-- 바닥 FLOOR: 지금 착용 슬롯처럼 1회 해금·착용. 착용 행 없음 = 기본(벽지 세트 바닥, 가구 기본 스킨과 같은 방식).
-- 방 소품 DECOR: 같은 아이템을 여러 개 산다(구매 1번 = 행 1개). 착용 슬롯이 아니라 student_look_equipment CHECK에는 넣지 않는다.
-- 캐릭터 착용 칸 ACCESSORY("소품", 손에 드는 것)와 다른 칸이다. 허용 목록만 넓혀 기존 행은 항상 통과한다.
ALTER TABLE look_item DROP CONSTRAINT ck_look_item_slot;
ALTER TABLE look_item ADD CONSTRAINT ck_look_item_slot CHECK (slot IN
    ('HAT', 'OUTFIT', 'ACCESSORY', 'BACKGROUND', 'DESK', 'WALL', 'WARDROBE', 'FLOOR', 'DECOR'));
ALTER TABLE student_look_equipment DROP CONSTRAINT ck_student_look_equipment_slot;
ALTER TABLE student_look_equipment ADD CONSTRAINT ck_student_look_equipment_slot CHECK (slot IN
    ('HAT', 'OUTFIT', 'ACCESSORY', 'BACKGROUND', 'DESK', 'WALL', 'WARDROBE', 'FLOOR'));

-- 방 소품 보유: 구매마다 1행, 그 구매의 원장 UNLOCK 행(사건 키 itemKey:Idempotency-Key)을 가리킨다(UK).
-- 보유 개수 = 학생·아이템별 행 수(아이템당 최대 8개는 잔액 행 잠금 아래 서비스가 검사). 아이템 슬롯이 DECOR인지도 서비스가 검사한다.
-- 새 테이블이라 NOT NULL 칸을 바로 둔다(SQL DEFAULT 없음).
CREATE TABLE student_room_decor (
    id uuid NOT NULL,
    student_id uuid NOT NULL,
    look_item_id uuid NOT NULL,
    ledger_id uuid NOT NULL,
    purchased_at timestamptz NOT NULL,
    CONSTRAINT pk_student_room_decor PRIMARY KEY (id),
    CONSTRAINT fk_student_room_decor_student_id FOREIGN KEY (student_id) REFERENCES student (id),
    CONSTRAINT fk_student_room_decor_look_item_id FOREIGN KEY (look_item_id) REFERENCES look_item (id),
    CONSTRAINT fk_student_room_decor_ledger_id FOREIGN KEY (ledger_id) REFERENCES reward_point_ledger (id),
    CONSTRAINT uk_student_room_decor_ledger_id UNIQUE (ledger_id)
);
CREATE INDEX ix_student_room_decor_student_item ON student_room_decor (student_id, look_item_id);

-- 방 소품 놓은 자리(1~8, 자리 종류 구분 없음). 같은 방 소품은 보유 개수만큼 여러 자리에 놓는다(서비스 검사).
-- 저장은 학생 행 잠금 아래 전체 교체(room_frame_slot과 같은 방식).
CREATE TABLE room_decor_spot (
    student_id uuid NOT NULL,
    spot_no smallint NOT NULL,
    look_item_id uuid NOT NULL,
    saved_at timestamptz NOT NULL,
    CONSTRAINT pk_room_decor_spot PRIMARY KEY (student_id, spot_no),
    CONSTRAINT fk_room_decor_spot_student_id FOREIGN KEY (student_id) REFERENCES student (id),
    CONSTRAINT fk_room_decor_spot_look_item_id FOREIGN KEY (look_item_id) REFERENCES look_item (id),
    CONSTRAINT ck_room_decor_spot_spot_no CHECK (spot_no BETWEEN 1 AND 8)
);
