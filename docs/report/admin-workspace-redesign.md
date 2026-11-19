# 관리자 화면 개선 및 인수인계

작성일: 2026-11-18

## 반영한 내용

- 관리자 로그인 화면과 공통 작업 화면, 권한별 메뉴 검색, 반응형 탐색 메뉴를 정리했다.
- 운영 현황, 작업 목록·상세, 감사 이력, 큐, 문의·공지, 결제·환불의 정보 배치와 상태 표시를 개선했다.
- 불필요한 안내 문구를 줄이고, 선택 상자 문구·화살표와 상태 배지의 간격을 조정했다.
- ISO 시각을 한국 시간의 날짜·시각으로 표시한다. 공용 알림 화면에도 같은 형식을 적용했다.
- 집계 기간을 직접 입력하거나 달력에서 시작일·종료일을 선택할 수 있다. 두 날짜를 선택해도 창은 유지되고, 확인으로 적용하거나 취소·Escape로 닫는다.
- 운영 요약의 학습 현황 카드와 바로가기 시작 위치, 카드 제목·아이콘·건수 정렬을 맞췄다.

주요 구현은 `frontend/web/src/presentation/admin/`에 있다. 기간 선택은 `PeriodPicker.tsx`와 `period-picker.css`, 공통 시각 표시는 `frontend/web/src/presentation/common/dateTime.ts`에서 관리한다.

## 검증

최종 커밋 전 다시 실행한 검사:

- `npm run build`: 통과
- `npm run lint`: 통과
- `npm run test:types`: 통과
- `node --test tests/adminDateTime.test.ts`: 2개 통과
- `git diff --check`: 통과

작업 과정에서는 관리자 메뉴·권한·목록·상세 창·알림, 기간 선택·취소·키보드 조작, 모델 관리와 인증 관련 브라우저 회귀를 확인했다. 관리자 14개 경로를 PC·태블릿·모바일 너비에서 점검했다. 관련 테스트는 다음 파일에 포함된다.

- `frontend/web/tests/browser/admin-workspace-design.spec.ts`
- `frontend/web/tests/browser/admin-period.spec.ts`
- `frontend/web/tests/browser/admin-missions.spec.ts`
- `frontend/web/tests/auth-browser/themeDrafts.spec.ts`
- `frontend/web/tests/model-browser/loading.spec.ts`
- `frontend/web/tests/model-browser/models.spec.ts`

브라우저 검증은 목업 또는 합성 API 응답을 사용한 로컬 검사이며, 운영 서버 검증이나 원격 CI 통과를 의미하지 않는다.

## 목업 실행

기존 프로젝트 설치 절차로 의존성을 준비한 뒤 `frontend/web`에서 실행한다. 아래는 PowerShell 예시다.

```powershell
$env:VITE_API_MOCK = 'true'
$env:VITE_SHARED_DEVICE_MOCK = 'false'
npm run dev -- --host localhost --port 5174 --strictPort
```

`http://localhost:5174/admin/login?entry=landing`에서 개발 목업 계정으로 로그인한다. 목업 화면에 안내되는 계정은 가상 계정이며 실제 서버 계정이 아니다. 개별 로컬 환경의 실제 계정 정보와 DB·브라우저 로그인 상태는 이 브랜치에 포함하지 않는다.

## 로그인 진단: 수정하지 않은 후속 항목

이번 변경은 인증 유지 시간·갱신·권한 정책을 바꾸지 않는다. 관리자 영구 자동 로그인을 추가한 상태도 아니다.

| 확인 항목 | 관찰 결과 및 후속 판단 |
|---|---|
| 목업 시간 만료 | 브라우저 시각을 16분 앞으로 변경해도 학생 홈 요청이 200으로 처리됐다. 목업은 가짜 토큰 일치 여부를 검사하며 실제 15분 만료를 모사하지 않는다. |
| 수동 만료 시연 | 학생 화면에서 ‘토큰 만료’를 선택하면 401 `TOKEN_EXPIRED` 후 학생 로그인으로 이동한다. 새로고침하지 않고 PIN을 다시 입력하면 학습 화면으로 복귀한다. |
| 가상 학생 새로고침 오류 | ‘가상 학생으로 PIN 로그인 준비’ → 표시된 PIN으로 로그인 → 새로고침 시 ‘이 기기에 등록된 친구가 없어요’가 나타나 PIN 재로그인이 막힌다. 기기 상태는 보존되지만 `pin-demo@example.test`의 자녀 목록이 `mockAccountChildren` 메모리에만 있어 복원되지 않는다. `mocks/handlers/studentDevice.ts`와 `mocks/fixtures/accounts.ts`의 복원 구조를 함께 확인해야 한다. |
| 다른 탭의 로그인 | 같은 브라우저·같은 출처에서 학부모 로그인은 기존 학생 탭을 유지했지만, 관리자 로그인은 학생 탭을 학생 로그인 화면으로 이동시켰다. 공통 `watchAuthChange` 처리의 영향이며 실서버까지 변경하기 전 정책 확인이 필요하다. |
| 다른 탭의 로그아웃 | 학부모·관리자 로그아웃 알림을 받으면 다른 학생·관리자 탭도 `/login`으로 이동한다. 관리자 인증이 풀렸을 때 관리자 로그인으로 안내하는 동작도 후속 검토 대상이다. |
| 목업 새 탭 복원 | 관리자 로그인 후 기존 탭의 새로고침은 유지됐지만, 별도 새 탭에서는 복원되지 않았다. 일반 목업의 로그인 상태는 탭별 `sessionStorage`에 저장된다. |

실서버의 현재 계약은 학생 access 기본 15분·refresh 미발급, 학부모·관리자 access 기본 15분·최초 로그인부터 최대 7일 세션이다. 학생 자동 갱신 도입은 위 목업 복원 오류 수정과 별개의 정책 변경이다. 기준은 [인증 API 명세](../design/api-spec.md)와 [인증 구현 보고서](auth-account.md)를 따른다.
