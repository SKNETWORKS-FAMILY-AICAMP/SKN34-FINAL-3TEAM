-- 실서버 E2E 전용 core_db 시드 (#246). compose.e2e.yaml의 e2e-seed가 마이그레이션 직후 실행, 재실행해도 결과 동일
-- 사용 변수: free_product_id (infrastructure/stubs/e2e.env PAYMENT_FREE_PRODUCT_ID)

-- 온보딩 필수 동의 문서
INSERT INTO consent_document (id, kind, version, title, content, required, effective_from, created_at) VALUES
  ('00000000-0000-4000-8000-0000000e2ec1', 'TERMS', 'e2e-1', 'E2E 이용약관', 'E2E 검증용 합성 문서', true, DATE '2026-01-01', now()),
  ('00000000-0000-4000-8000-0000000e2ec2', 'PRIVACY', 'e2e-1', 'E2E 개인정보 처리방침', 'E2E 검증용 합성 문서', true, DATE '2026-01-01', now()),
  ('00000000-0000-4000-8000-0000000e2ec3', 'GUARDIAN', 'e2e-1', 'E2E 보호자 동의', 'E2E 검증용 합성 문서', true, DATE '2026-01-01', now())
ON CONFLICT DO NOTHING;

-- 무료(기본 이용권)·유료(결제 E2E) 상품. features는 값을 명시한다(#506: 값이 없으면 무료 추가 문제는 거부, 일요일은 V43과 같게).
-- 무료 extraMissions=true는 E2E 전용: 학습 여정(learning-journey.spec.ts)이 테마 시드 없이 무료 학생으로 추가 문제를 푼다
-- (운영 무료 상품은 V43으로 false, core-gateway 13절 "다시 켜기" 경로). 무료 추가 문제는 하루 dailyMissions개
INSERT INTO product (id, code, name, price, billing_cycle, child_limit, features, limits, active, created_at) VALUES
  (:'free_product_id'::uuid, 'E2E-FREE', 'E2E 무료', 0, 'MONTHLY', 1, '{"extraMissions":true,"sundayTheme":false}',
   '{"dailyMissions":1,"dailyConversations":0,"reportNarrative":false}', true, now()),
  ('00000000-0000-4000-8000-0000000e2e02', 'E2E-PLUS', 'E2E 프리미엄', 14900, 'MONTHLY', 1, '{"sundayTheme":true}',
   '{"dailyConversations":30,"reportNarrative":true}', true, now())
ON CONFLICT DO NOTHING;

-- 관리자: google-stub sub 'e2e-admin'으로 로그인, 전체 권한
INSERT INTO user_account (id, role, login_id, password_hash, display_name, status, is_demo, created_at, updated_at, oauth_provider, oauth_subject)
VALUES ('00000000-0000-4000-8000-0000000e2ea1', 'ADMIN', 'e2e-admin@example.test', NULL, 'E2E 관리자', 'ACTIVE', false, now(), now(), 'GOOGLE', 'e2e-admin')
ON CONFLICT DO NOTHING;

INSERT INTO admin_permission (user_id, permission, granted_by, granted_at)
SELECT '00000000-0000-4000-8000-0000000e2ea1', permission, '00000000-0000-4000-8000-0000000e2ea1', now()
FROM (VALUES ('CONTENT'), ('PAYMENT_VIEW'), ('PAYMENT_REFUND'), ('SERVICE_OPS')) AS p(permission)
ON CONFLICT DO NOTHING;
