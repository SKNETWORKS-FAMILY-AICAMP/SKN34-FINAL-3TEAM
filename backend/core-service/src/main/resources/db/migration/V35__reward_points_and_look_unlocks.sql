-- #389 참여 포인트(P21)·꾸미기 해금(P22). 결제와 분리된 core reward 도메인이다.
-- 포인트는 참여로만 적립(판정 결과 무관)하고 순위·소멸·회수가 없다. 해금은 영구이며 즉시 차감·환급 없음.
-- 모든 새 테이블은 빈 상태로 만들어지므로 NOT NULL 컬럼을 바로 둔다(SQL DEFAULT 없음).

-- 적립 규칙: 값·하루 상한을 데이터로 관리한다. daily_cap은 한국 시간 하루 적립 횟수 상한(NULL이면 없음).
CREATE TABLE reward_rule (
    event_type varchar(32) NOT NULL,
    amount int NOT NULL,
    daily_cap int,
    active boolean NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT pk_reward_rule PRIMARY KEY (event_type),
    CONSTRAINT ck_reward_rule_event_type CHECK (event_type IN
        ('MISSION_COMPLETED', 'REVIEW_VIEWED', 'COMMUNITY_POSTED', 'REACTION_GIVEN', 'THEME_COMPLETED')),
    CONSTRAINT ck_reward_rule_amount CHECK (amount > 0),
    CONSTRAINT ck_reward_rule_daily_cap CHECK (daily_cap IS NULL OR daily_cap > 0)
);

-- P21 초기값(2026-11-06·11-07 결정): 학습 완료 10·되돌아보기 10·공유 5·반응 1(하루 5회)·완주 30.
INSERT INTO reward_rule (event_type, amount, daily_cap, active, updated_at) VALUES
    ('MISSION_COMPLETED', 10, NULL, true, TIMESTAMPTZ '2026-11-07 00:00:00+09'),
    ('REVIEW_VIEWED', 10, NULL, true, TIMESTAMPTZ '2026-11-07 00:00:00+09'),
    ('COMMUNITY_POSTED', 5, NULL, true, TIMESTAMPTZ '2026-11-07 00:00:00+09'),
    ('REACTION_GIVEN', 1, 5, true, TIMESTAMPTZ '2026-11-07 00:00:00+09'),
    ('THEME_COMPLETED', 30, NULL, true, TIMESTAMPTZ '2026-11-07 00:00:00+09');

-- 원장: 사건당 한 행. UK (student_id, event_type, source_key)가 같은 사건의 두 번째 적립·같은 항목 두 번째 차감을 막는다.
CREATE TABLE reward_point_ledger (
    id uuid NOT NULL,
    student_id uuid NOT NULL,
    event_type varchar(32) NOT NULL,
    source_key varchar(200) NOT NULL,
    amount int NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_reward_point_ledger PRIMARY KEY (id),
    CONSTRAINT fk_reward_point_ledger_student_id FOREIGN KEY (student_id) REFERENCES student (id),
    CONSTRAINT uk_reward_point_ledger_event UNIQUE (student_id, event_type, source_key),
    CONSTRAINT ck_reward_point_ledger_event_type CHECK (event_type IN
        ('MISSION_COMPLETED', 'REVIEW_VIEWED', 'COMMUNITY_POSTED', 'REACTION_GIVEN', 'THEME_COMPLETED', 'UNLOCK')),
    CONSTRAINT ck_reward_point_ledger_source_key CHECK (length(source_key) > 0),
    -- 적립은 양수, 해금 사용은 음수
    CONSTRAINT ck_reward_point_ledger_sign CHECK ((event_type = 'UNLOCK') = (amount < 0) AND amount <> 0)
);
CREATE INDEX ix_reward_point_ledger_student_created ON reward_point_ledger (student_id, created_at);

-- 잔액: 원장과 같은 트랜잭션에서 갱신하고, 적립·해금은 이 행 잠금으로 학생별 직렬화한다.
CREATE TABLE reward_point_balance (
    student_id uuid NOT NULL,
    balance int NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT pk_reward_point_balance PRIMARY KEY (student_id),
    CONSTRAINT fk_reward_point_balance_student_id FOREIGN KEY (student_id) REFERENCES student (id),
    CONSTRAINT ck_reward_point_balance_balance CHECK (balance >= 0)
);

-- 관리자 등록 캐릭터 아이템(모자·옷·소품·배경). 삭제 없이 판매 중단만 한다.
-- code는 대문자·숫자·밑줄이라 THEME:·COMPANION: 키와 겹치지 않는다.
CREATE TABLE look_item (
    id uuid NOT NULL,
    code varchar(40) NOT NULL,
    slot varchar(16) NOT NULL,
    name varchar(40) NOT NULL,
    price_points int NOT NULL,
    asset_key varchar(200) NOT NULL,
    status varchar(16) NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT pk_look_item PRIMARY KEY (id),
    CONSTRAINT uk_look_item_code UNIQUE (code),
    CONSTRAINT fk_look_item_created_by FOREIGN KEY (created_by) REFERENCES user_account (id),
    CONSTRAINT ck_look_item_code_format CHECK (code ~ '^[A-Z0-9_]{3,40}$'),
    CONSTRAINT ck_look_item_slot CHECK (slot IN ('HAT', 'OUTFIT', 'ACCESSORY', 'BACKGROUND')),
    CONSTRAINT ck_look_item_name CHECK (length(btrim(name)) > 0),
    CONSTRAINT ck_look_item_price_points CHECK (price_points > 0),
    CONSTRAINT ck_look_item_status CHECK (status IN ('ON_SALE', 'STOPPED'))
);

-- 해금: 테마·캐릭터는 THEME:<code>·COMPANION:<code>, 아이템은 look_item.code. 무료 lake·mungchi는 행 없이 항상 해금.
-- ledger_id는 포인트 해금 원장 행, 잠금 적용 전 저장 값을 옮긴 행은 NULL.
CREATE TABLE student_look_unlock (
    student_id uuid NOT NULL,
    item_key varchar(64) NOT NULL,
    ledger_id uuid,
    unlocked_at timestamptz NOT NULL,
    CONSTRAINT pk_student_look_unlock PRIMARY KEY (student_id, item_key),
    CONSTRAINT fk_student_look_unlock_student_id FOREIGN KEY (student_id) REFERENCES student (id),
    CONSTRAINT fk_student_look_unlock_ledger_id FOREIGN KEY (ledger_id) REFERENCES reward_point_ledger (id),
    CONSTRAINT uk_student_look_unlock_ledger_id UNIQUE (ledger_id)
);

-- 착용: 학생·슬롯당 아이템 하나. 해금 여부와 아이템 슬롯 일치는 서비스가 검사한다.
CREATE TABLE student_look_equipment (
    student_id uuid NOT NULL,
    slot varchar(16) NOT NULL,
    look_item_id uuid NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT pk_student_look_equipment PRIMARY KEY (student_id, slot),
    CONSTRAINT fk_student_look_equipment_student_id FOREIGN KEY (student_id) REFERENCES student (id),
    CONSTRAINT fk_student_look_equipment_look_item_id FOREIGN KEY (look_item_id) REFERENCES look_item (id),
    CONSTRAINT ck_student_look_equipment_slot CHECK (slot IN ('HAT', 'OUTFIT', 'ACCESSORY', 'BACKGROUND'))
);

-- 잠금 적용 전 저장한 테마·캐릭터는 해금된 것으로 이관(P22 "잠금 전 선택 항목은 해금 간주"). 포인트 차감 없음.
INSERT INTO student_look_unlock (student_id, item_key, ledger_id, unlocked_at)
SELECT id, 'THEME:' || look_theme, NULL, look_updated_at FROM student
WHERE look_theme IS NOT NULL AND look_theme <> 'lake';
INSERT INTO student_look_unlock (student_id, item_key, ledger_id, unlocked_at)
SELECT id, 'COMPANION:' || look_companion, NULL, look_updated_at FROM student
WHERE look_companion IS NOT NULL AND look_companion <> 'mungchi';
