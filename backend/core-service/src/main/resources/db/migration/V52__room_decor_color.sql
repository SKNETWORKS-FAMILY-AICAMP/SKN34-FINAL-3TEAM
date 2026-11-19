-- #758: 색은 아이템이 아니라 놓은 자리마다 저장한다. 기존 행은 기본 색(NULL).
ALTER TABLE room_decor_spot ADD COLUMN color varchar(20) NULL;
ALTER TABLE room_decor_spot ADD CONSTRAINT ck_room_decor_spot_color
    CHECK (color IS NULL OR color ~ '^[a-z0-9-]{1,20}$');
