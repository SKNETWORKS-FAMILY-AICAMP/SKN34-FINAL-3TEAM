# #914 관리자 글자 대비·가로 스크롤 표 재점검 (2026-11-23)

#885 실서버 UX 점검에서 남은 관리자 axe serious 위반(`color-contrast`, `scrollable-region-focusable`)을 고친 뒤 같은 방식으로 다시 점검한 원본 결과.

- 수행 구분: 모의(대역 compose). `compose.yaml`·`compose.minio.yaml`·`compose.e2e.yaml`(프로젝트 `sagomungchi-e2e`, `infrastructure/stubs/e2e.env`)을 이 브랜치에서 새로 빌드해 띄우고, 웹은 `playwright.e2e.config.ts`의 Vite dev(`VITE_API_MOCK=false`)로 실제 core에 연결
- 도구: axe-core 4.10.2, 태그 `wcag2a`·`wcag2aa`·`wcag21aa`·`wcag22aa`, impact serious·critical만 기록
- 화면: 관리자 로그인, 시드 관리자(`e2e-admin`)로 로그인한 뒤 메뉴 16개(운영 현황·감사 이력·미션 관리·미션 초안·주간 테마 검수·게시 관리·꾸미기 아이템·문의·공지·오류 신고·작업 재처리·작업 대기열·모델·프롬프트·표현 검토·AI 사용량·결제·환불), 상세(미션 편집·테마 초안 상세). 폭 1440×900, 390×844
- 데이터: 새로 띄운 스택의 시드만 있음(작업 목록이 비어 작업 상세는 열지 못함). #885 점검 때의 성취기준 시드·실패 초안은 넣지 않음

| 파일 | 내용 |
|---|---|
| `axe-audit.spec.ts` | 점검 스크립트. `frontend/web/tests/e2e/`에 복사하고 `AXE_PATH`(axe.min.js)·`AXE_OUT`(결과 파일)을 지정해 `npx playwright test -c playwright.e2e.config.ts axe-audit` |
| `axe-before.jsonl` | 고치기 전(develop `e9463dbe`의 `src/presentation/admin`) 화면 36개, serious 191건(`color-contrast` 186, `scrollable-region-focusable` 5) |
| `axe-after.jsonl` | 고친 뒤 같은 36개 화면, serious 0건 |

각 줄은 화면 하나: `name`(메뉴 이름), `w`(폭), `url`(경로), `n`(위반 노드 수), `r`(규칙별 선택자·글자색·배경색·대비). 학생 원문·비밀 값 없음.
