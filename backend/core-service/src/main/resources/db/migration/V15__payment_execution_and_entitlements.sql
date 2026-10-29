-- #48 preserves V1..V13 and reserves V14 for #46 support.
ALTER TABLE payment_order ADD COLUMN product_snapshot jsonb;
ALTER TABLE subscription ADD COLUMN product_snapshot jsonb;
ALTER TABLE subscription ADD COLUMN billing_anchor_day integer CHECK (billing_anchor_day BETWEEN 1 AND 31);
-- Historical rows need operator-approved backfill before automated charging.
ALTER TABLE subscription ADD COLUMN last_billing_attempt_date date;
ALTER TABLE subscription ADD COLUMN revision bigint;
UPDATE subscription SET revision=0;
ALTER TABLE subscription ALTER COLUMN revision SET NOT NULL;
ALTER TABLE refund_request ADD COLUMN cancel_key uuid;
ALTER TABLE refund_request ADD COLUMN usage_verified_at timestamptz;
ALTER TABLE refund_request ADD CONSTRAINT uq_refund_cancel_key UNIQUE(cancel_key);
CREATE UNIQUE INDEX uq_refund_unresolved_payment ON refund_request(payment_id)
    WHERE status IN ('REQUESTED','APPROVED','FAILED');

CREATE TABLE payment_charge_attempt (
 id uuid PRIMARY KEY,
 order_id uuid NOT NULL REFERENCES payment_order(id),
 attempt_no integer NOT NULL CHECK (attempt_no BETWEEN 0 AND 3),
 pg_order_no varchar NOT NULL UNIQUE,
 idempotency_key uuid NOT NULL UNIQUE,
 status varchar NOT NULL CHECK (status IN ('CONFIRMING','APPROVED','FAILED','CANCELED')),
 payment_key varchar,
 failure_code varchar,
 started_at timestamptz NOT NULL,
 updated_at timestamptz NOT NULL,
 UNIQUE(order_id,attempt_no)
);
CREATE UNIQUE INDEX uq_charge_live_order ON payment_charge_attempt(order_id) WHERE status IN ('CONFIRMING','APPROVED');
CREATE INDEX ix_charge_recovery ON payment_charge_attempt(status,updated_at);

CREATE TABLE payment_premium_usage (
 id uuid PRIMARY KEY,
 student_id uuid NOT NULL REFERENCES student(id),
 subscription_id uuid NOT NULL REFERENCES subscription(id),
 kind varchar NOT NULL CHECK (kind IN ('FEEDBACK','CONVERSATION','REPORT_VIEW')),
 source_id uuid NOT NULL,
 status varchar NOT NULL CHECK (status IN ('RESERVED','USED','FAILED')),
 created_at timestamptz NOT NULL,
 updated_at timestamptz NOT NULL,
 UNIQUE(kind,source_id)
);
CREATE INDEX ix_payment_usage_refund ON payment_premium_usage(student_id,created_at,status);
