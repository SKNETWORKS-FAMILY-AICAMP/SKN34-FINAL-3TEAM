-- 운영 관측 상태이며 승인·평가 근거와 분리한다. 프로세스 기동마다 instance_id 변경.
CREATE TABLE model_loading_report (
    instance_id uuid PRIMARY KEY,
    pod_id varchar(253) NOT NULL,
    sequence bigint NOT NULL CHECK (sequence > 0),
    reported_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL,
    models jsonb NOT NULL CHECK (jsonb_typeof(models) = 'array')
);
CREATE INDEX ix_model_loading_report_pod_time ON model_loading_report(pod_id, reported_at DESC);
CREATE INDEX ix_model_loading_report_time ON model_loading_report(reported_at);
