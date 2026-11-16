-- #388 P20 커뮤니티 준비 버전: 학생 공개 설정 컬럼(nullable), 선택 동의 COMMUNITY, 신고 대상 COMMUNITY_POST.
-- community_enabled는 다음 버전에서 기존 행을 false로 채운 뒤 NOT NULL·기본값 false(검증 스크립트 명시 예외)로 바꾼다.
ALTER TABLE student ADD COLUMN community_enabled boolean,
    ADD COLUMN community_updated_at timestamptz;

ALTER TABLE consent_document DROP CONSTRAINT ck_consent_document_kind,
    ADD CONSTRAINT ck_consent_document_kind CHECK (kind IN ('TERMS', 'PRIVACY', 'GUARDIAN', 'COMMUNITY'));

ALTER TABLE error_report DROP CONSTRAINT ck_error_report_target_type,
    ADD CONSTRAINT ck_error_report_target_type
        CHECK (target_type IN ('FOLLOWUP', 'JUDGMENT', 'ANALYSIS', 'REPORT', 'COMMUNITY_POST'));
ALTER TABLE correction DROP CONSTRAINT ck_correction_target_type,
    ADD CONSTRAINT ck_correction_target_type
        CHECK (target_type IN ('FOLLOWUP', 'JUDGMENT', 'ANALYSIS', 'REPORT', 'COMMUNITY_POST'));

-- 선택 동의 문서(자녀 단위). 개정은 새 (kind, version) 행으로만 하고 이 행은 고치지 않는다.
INSERT INTO consent_document(id, kind, version, title, content, required, effective_from, created_at) VALUES
('00000000-0000-4000-8000-000003880001', 'COMMUNITY', '1.0', '풀이 공유 커뮤니티 이용 동의서(선택)', $consent$※ 이 문서는 교육 과정 시연용 문서이며 법률 검토를 거치지 않았습니다.
※ [초안] 2026-11-06 서비스 결정(P20)을 바탕으로 작성한 확정 전 초안입니다.

풀이 공유 커뮤니티 이용 동의서(선택)

사고뭉치 프로젝트팀(SKN34 3팀)은 자녀가 같은 미션을 마무리한 다른 학생과 생각을 나눌 수 있도록 아래와 같이 자녀의 정보를 다른 학생에게 보여 주고자 합니다.

▸ 공개하는 정보
 - 자녀가 커뮤니티 공개를 켠 뒤 미션을 처음 마무리한 시도의 마지막 답변(메모·판정·되묻기는 공개하지 않음)
 - 자녀의 별명과 꾸미기 캐릭터

▸ 공개 범위와 방법
 - 같은 미션을 마무리한 사고뭉치 학생에게만 보여 주며, 학부모에게는 자기 자녀의 공유물과 받은 반응만 보여 줍니다.
 - 다른 학생은 정해진 반응 4가지만 남길 수 있고, 반응 수는 자녀와 학부모만 볼 수 있습니다.
 - 부적절한 표현으로 신고된 공유물은 즉시 숨기고 운영자가 검토합니다.

▸ 보유·이용 기간
 - 동의 철회, 자녀 기록 삭제 또는 회원 탈퇴 시까지. 동의를 철회하거나 자녀가 공개를 끄면 공유물은 즉시 비공개가 되고, 자녀 기록 삭제·회원 탈퇴 시 공유물과 남긴 반응은 파기됩니다.

 ※ 이 동의는 선택 사항이며 동의하지 않아도 학습 서비스는 모두 이용할 수 있습니다. 동의하지 않으면 자녀가 커뮤니티 공개를 켤 수 없습니다.
 ※ 동의한 뒤에도 공개 여부는 자녀가 직접 켜고 끕니다. 학부모는 언제든지 동의 관리 화면에서 동의를 철회할 수 있습니다.

 ☞ 위와 같이 자녀의 풀이를 같은 미션을 마무리한 학생에게 공개하는 데 법정대리인으로서 동의합니다.

사고뭉치 프로젝트팀(SKN34 3팀) 귀중$consent$, false, DATE '2026-11-08', CURRENT_TIMESTAMP);
