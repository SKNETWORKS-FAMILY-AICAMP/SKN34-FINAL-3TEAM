# develop 충돌 해결 통합본 — 2026-10-29

## 작업 위치

- `C:\Users\playdata2\Documents\GitHub\SKN34-FINAL-3TEAM-fe-integration`
- 브랜치 `fix/web-develop-integration`
- 기존 HEAD `5b898ec` + develop `f9df2d3`의 일반 merge를 `--no-commit --no-ff`로 준비했다.
- 원본 `SKN34-FINAL-3TEAM-fe-requirements`의 브랜치·미커밋 변경·미추적 파일을 변경하지 않았다.
- 기존 미커밋 tracked 변경은 저장소 밖 `C:\Users\playdata2\fe-134-before-integration.patch`로 보존하고 통합본에 3-way 적용했다. 새 계약 테스트 2개도 복사했다.
- 이전 인수인계 파일·구버전 PDF는 원본에 그대로 있다. 무조건 PR에 추가하지 않았다.

## 해결

실제 충돌은 `frontend/web/src/presentation/router.tsx` 1개였다.
- 도움말·공지·알림·계정 관리 등 기존 요구사항 보완 경로 유지.
- `/support`는 역할당 한 번만 등록.
- 학생·학부모 `/support?reportId=…` 또는 `?inquiryId=…`는 develop의 실제 DTO 조회 화면 `SupportResults`로 연결. 원래 알림 주소·쿼리를 보존.
- 학생·학부모 `/support/results`에 결과 목록 경로 추가, 접수 화면 메뉴에서 연결.
- 쿼리 없는 `/support`는 기존 접수 화면, 관리자 `/support`는 관리자 화면 유지.
- `support/SupportEntry.tsx`에서 분기하여 router의 Fast Refresh lint 경고 방지.
- develop의 관리자 운영·판정 정정 코드와 클로드 #134 변경 모두 보존.

## 검증

- 단위·계약 테스트 111개 통과.
- TypeScript·Vite 빌드, lint, 운영 목업 제외 검사 통과.
- 확장한 api-mode-browser 통과: 학부모 알림 링크 2종, 결과 목록, 접수 화면, 학생 결과 목록 진입. Chrome 두 탭, 동시 refresh 최대 1, 학생 refresh 없음, pageErrors=[] 확인.
- 이 브라우저 검증은 운영 빌드 + API 대역이며 실제 backend/DB 통합은 아님.
- `git diff --name-only --diff-filter=U` 비어 있음. index·작업 트리의 공백 검사 통과.
- JS 청크 500kB 초과 경고는 기존대로 남음.

## 상태와 후속

- 충돌 해결 내용을 index에 반영했다. merge는 커밋 전 상태이며 MERGE_HEAD가 존재하는 것이 정상이다. 새로운 merge나 pull을 겹쳐 실행하지 말 것.
- 자동 커밋 금지 지침을 유지하여 커밋·push·PR 수정은 하지 않았다. GitHub #124 충돌 표시는 아직 그대로다.
- 이 통합 브랜치에는 #124 범위와 #134 후속 수정이 함께 있다. 어느 원격 브랜치로 게시할지 결정한 뒤 범위를 확인하고 커밋해야 한다.
- 기존 접수/공지/관리자 문의 API의 제안 DTO와 새 core 지원 계약 전체를 맞추는 작업은 별개로 남아 있다. 이번 작업은 경로 충돌 및 알림 결과 화면 보존을 해결했으며, 지원 기능 전체 실서버 연동 완료를 뜻하지 않는다.
- 현재 5230 데모는 원본 작업 폴더 서버다. 통합본은 이 폴더의 frontend/web에서 별도 포트로 실행하거나 기존 서버를 명시적으로 재시작해야 보인다.

## 게시 승인 후 갱신

사용자가 "충돌 해결된 거 기준으로 PR 다시 올려"라고 요청하여 이 통합 브랜치의 병합 커밋·push·develop 대상 새 PR 생성을 승인했다. 위 '커밋 전' 기록은 충돌 해결 당시 상태이며, 이후 게시 결과는 Git 이력 및 새 PR을 따른다. 기존 #124를 대체하는 통합 PR로 게시하고 기존 PR은 임의로 닫지 않는다.
