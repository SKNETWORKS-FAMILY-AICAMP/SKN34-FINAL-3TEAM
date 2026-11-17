-- #723: 고정 자리 번호를 바닥·벽 기준 칸으로 바꾼다. V50은 수정하지 않는다.
-- 운영·공유 DB에 기존 행이 있으면 자동 삭제·임의 좌표 변환 없이 중단한다.
-- 같은 Flyway 트랜잭션의 잠금으로 검사 뒤 옛 배치가 추가되지 않게 한다.
LOCK TABLE room_decor_spot IN ACCESS EXCLUSIVE MODE;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM room_decor_spot) THEN
        RAISE EXCEPTION 'V51: room_decor_spot contains existing placements; review their disposition before migrating (#723). No rows were deleted.';
    END IF;
END
$$;

ALTER TABLE room_decor_spot
    DROP CONSTRAINT pk_room_decor_spot,
    DROP CONSTRAINT ck_room_decor_spot_spot_no,
    DROP COLUMN spot_no,
    ADD COLUMN surface varchar(16) NOT NULL,
    ADD COLUMN cell_col smallint NOT NULL,
    ADD COLUMN cell_row smallint NOT NULL,
    ADD CONSTRAINT pk_room_decor_spot PRIMARY KEY (student_id, surface, cell_col, cell_row),
    ADD CONSTRAINT ck_room_decor_spot_surface CHECK (surface IN ('FLOOR', 'WALL_BACK', 'WALL_LEFT')),
    ADD CONSTRAINT ck_room_decor_spot_cell CHECK (
        (surface = 'FLOOR' AND cell_col BETWEEN 0 AND 16 AND cell_row BETWEEN 0 AND 12)
        OR (surface = 'WALL_BACK' AND cell_col BETWEEN 0 AND 15 AND cell_row BETWEEN 0 AND 5)
        OR (surface = 'WALL_LEFT' AND cell_col BETWEEN 0 AND 10 AND cell_row BETWEEN 0 AND 5)
    );
