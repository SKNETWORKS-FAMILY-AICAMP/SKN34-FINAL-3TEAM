-- Initial schema: docs/design/erd.md section 3.4.
-- IDs and timestamps are supplied by the application. No seed data.

CREATE TABLE product (
    id uuid NOT NULL,
    code varchar NOT NULL,
    name varchar NOT NULL,
    price integer,
    billing_cycle varchar NOT NULL,
    child_limit integer NOT NULL,
    features jsonb NOT NULL,
    active boolean NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_product PRIMARY KEY (id),
    CONSTRAINT uq_product_code
        UNIQUE (code),
    CONSTRAINT ck_product_code
        CHECK (code IN ('BASIC', 'PLUS')),
    CONSTRAINT ck_product_billing_cycle
        CHECK (billing_cycle IN ('MONTHLY', 'YEARLY'))
);

CREATE TABLE payment_order (
    id uuid NOT NULL,
    order_no varchar NOT NULL,
    parent_user_id uuid NOT NULL,
    student_id uuid NOT NULL,
    product_id uuid NOT NULL,
    subscription_id uuid,
    kind varchar NOT NULL,
    billing_period_start date,
    amount integer NOT NULL,
    trace_id varchar,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_payment_order PRIMARY KEY (id),
    CONSTRAINT uq_payment_order_order_no
        UNIQUE (order_no),
    CONSTRAINT ck_payment_order_kind
        CHECK (kind IN ('INITIAL', 'RENEWAL'))
);

CREATE TABLE payment (
    id uuid NOT NULL,
    order_id uuid NOT NULL,
    payment_key varchar,
    amount integer NOT NULL,
    status varchar NOT NULL,
    method varchar,
    entitlement_status varchar,
    failure_code varchar,
    approved_at timestamptz,
    canceled_at timestamptz,
    updated_at timestamptz NOT NULL,
    CONSTRAINT pk_payment PRIMARY KEY (id),
    CONSTRAINT uq_payment_order_id
        UNIQUE (order_id),
    CONSTRAINT uq_payment_payment_key
        UNIQUE (payment_key),
    CONSTRAINT ck_payment_status
        CHECK (status IN (
            'APPROVED',
            'CONFIRMING',
            'FAILED',
            'CANCELED',
            'REFUND_REVIEW',
            'REFUNDED'
        )),
    CONSTRAINT ck_payment_entitlement_status
        CHECK (entitlement_status IN ('APPLIED', 'RECOVERY_REQUIRED'))
);

CREATE TABLE subscription (
    id uuid NOT NULL,
    parent_user_id uuid NOT NULL,
    student_id uuid NOT NULL,
    product_id uuid NOT NULL,
    status varchar NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    next_billing_date date,
    auto_renew boolean NOT NULL,
    customer_key varchar,
    billing_key_enc varchar,
    renewal_retry_count integer,
    grace_until date,
    auto_renew_canceled_at timestamptz,
    canceled_at timestamptz,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT pk_subscription PRIMARY KEY (id),
    CONSTRAINT ck_subscription_status
        CHECK (status IN ('ACTIVE', 'RENEWAL_FAILED', 'CANCELED'))
);

CREATE TABLE refund_request (
    id uuid NOT NULL,
    payment_id uuid NOT NULL,
    requested_by uuid NOT NULL,
    amount integer NOT NULL,
    reason text NOT NULL,
    status varchar NOT NULL,
    decided_by uuid,
    reject_reason text,
    pg_status varchar,
    decided_at timestamptz,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_refund_request PRIMARY KEY (id),
    CONSTRAINT ck_refund_request_status
        CHECK (status IN ('REQUESTED', 'APPROVED', 'REJECTED', 'COMPLETED', 'FAILED'))
);

CREATE TABLE pg_webhook_event (
    id uuid NOT NULL,
    transmission_id varchar NOT NULL,
    event_type varchar NOT NULL,
    order_no varchar,
    result varchar NOT NULL,
    received_at timestamptz NOT NULL,
    processed_at timestamptz,
    CONSTRAINT pk_pg_webhook_event PRIMARY KEY (id),
    CONSTRAINT uq_pg_webhook_event_transmission_id
        UNIQUE (transmission_id),
    CONSTRAINT ck_pg_webhook_event_result
        CHECK (result IN ('APPLIED', 'IGNORED', 'FAILED'))
);

ALTER TABLE payment_order
    ADD CONSTRAINT fk_payment_order_parent_user_id
    FOREIGN KEY (parent_user_id) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE payment_order
    ADD CONSTRAINT fk_payment_order_student_id
    FOREIGN KEY (student_id) REFERENCES student (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE payment_order
    ADD CONSTRAINT fk_payment_order_product_id
    FOREIGN KEY (product_id) REFERENCES product (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE payment_order
    ADD CONSTRAINT fk_payment_order_subscription_id
    FOREIGN KEY (subscription_id) REFERENCES subscription (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE payment
    ADD CONSTRAINT fk_payment_order_id
    FOREIGN KEY (order_id) REFERENCES payment_order (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE subscription
    ADD CONSTRAINT fk_subscription_parent_user_id
    FOREIGN KEY (parent_user_id) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE subscription
    ADD CONSTRAINT fk_subscription_student_id
    FOREIGN KEY (student_id) REFERENCES student (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE subscription
    ADD CONSTRAINT fk_subscription_product_id
    FOREIGN KEY (product_id) REFERENCES product (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE refund_request
    ADD CONSTRAINT fk_refund_request_payment_id
    FOREIGN KEY (payment_id) REFERENCES payment (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE refund_request
    ADD CONSTRAINT fk_refund_request_requested_by
    FOREIGN KEY (requested_by) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

ALTER TABLE refund_request
    ADD CONSTRAINT fk_refund_request_decided_by
    FOREIGN KEY (decided_by) REFERENCES user_account (id)
    ON DELETE NO ACTION ON UPDATE NO ACTION;

CREATE UNIQUE INDEX uq_payment_order_renewal_period
    ON payment_order (subscription_id, billing_period_start)
    WHERE kind = 'RENEWAL';

CREATE INDEX ix_payment_status_updated
    ON payment (status, updated_at);

CREATE UNIQUE INDEX uq_subscription_active_student
    ON subscription (student_id)
    WHERE status IN ('ACTIVE', 'RENEWAL_FAILED');

CREATE INDEX ix_subscription_next_billing
    ON subscription (next_billing_date)
    WHERE auto_renew;
