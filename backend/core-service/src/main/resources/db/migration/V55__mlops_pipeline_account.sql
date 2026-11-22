-- #728 재학습 자동 등록 계정 (에픽 #688, 설계 #725, docs/design/erd.md 3.5·api-spec 5.2.3).
-- 표현 분류 재학습 작업(ops 토큰)이 모델을 REGISTERED로 올릴 때 audit_log.actor_user_id(NOT NULL FK)로만 쓴다.
-- admin_credential·admin_permission을 두지 않아 로그인·활성화를 할 수 없다. ID는 app.model-registry.pipeline-actor-id와 같아야 한다.
INSERT INTO user_account (id, role, login_id, password_hash, oauth_provider, oauth_subject, display_name, status, is_demo,
                          created_at, updated_at, withdrawn_at)
VALUES ('00000000-0000-4000-8000-0000000f0725', 'ADMIN', 'mlops-pipeline@system.invalid', NULL, NULL, NULL, 'MLOps 파이프라인',
        'ACTIVE', false, now(), now(), NULL)
ON CONFLICT DO NOTHING;
