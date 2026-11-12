-- #555 생활공간(P27·P22 개정, 2026-11-12). V35는 고치지 않고 이 버전에서 바꾼다.
-- 가구 스킨: 고정 가구 책상(DESK)·추억의 벽(WALL)·옷장(WARDROBE)을 꾸미기 아이템 슬롯으로 더한다.
-- 가구 1개 = 착용 슬롯 1개라 기존 PK (student_id, slot)가 가구당 스킨 1개를 보장한다.
-- 가구별 기본 스킨은 행이 없다(착용 행 없음 = 기본 스킨, 테마 lake·기본 벽지와 같은 방식).
ALTER TABLE look_item DROP CONSTRAINT ck_look_item_slot;
ALTER TABLE look_item ADD CONSTRAINT ck_look_item_slot CHECK (slot IN
    ('HAT', 'OUTFIT', 'ACCESSORY', 'BACKGROUND', 'DESK', 'WALL', 'WARDROBE'));
ALTER TABLE student_look_equipment DROP CONSTRAINT ck_student_look_equipment_slot;
ALTER TABLE student_look_equipment ADD CONSTRAINT ck_student_look_equipment_slot CHECK (slot IN
    ('HAT', 'OUTFIT', 'ACCESSORY', 'BACKGROUND', 'DESK', 'WALL', 'WARDROBE'));

-- 추억의 벽 액자 슬롯(1~6). 회차 키 (theme_id, theme_week_start)는 learning theme_frame 논리 참조라
-- 서비스 간 FK가 없고 저장 전에 learning 내부 API로 보유를 확인한다. 같은 액자는 한 슬롯에만 건다.
-- 새 테이블이라 NOT NULL 칸을 바로 둔다(SQL DEFAULT 없음).
CREATE TABLE room_frame_slot (
    student_id uuid NOT NULL,
    slot_no smallint NOT NULL,
    theme_id uuid NOT NULL,
    theme_week_start date NOT NULL,
    saved_at timestamptz NOT NULL,
    CONSTRAINT pk_room_frame_slot PRIMARY KEY (student_id, slot_no),
    CONSTRAINT fk_room_frame_slot_student_id FOREIGN KEY (student_id) REFERENCES student (id),
    CONSTRAINT uk_room_frame_slot_frame UNIQUE (student_id, theme_id, theme_week_start),
    CONSTRAINT ck_room_frame_slot_slot_no CHECK (slot_no BETWEEN 1 AND 6),
    -- 회차 주는 KST 월요일(learning theme_week_start와 같은 값)
    CONSTRAINT ck_room_frame_slot_week_start CHECK (extract(isodow FROM theme_week_start) = 1)
);
