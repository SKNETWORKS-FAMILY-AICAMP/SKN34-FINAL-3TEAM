# #917 관리자 처리 중 단추 키보드 초점 확인 (2026-11-23)

#885 추가 확인에서 관리자 "꾸미기 아이템 › 새 아이템" 저장과 "주간 테마 검수 › 새 테마 초안 요청"을 키보드로 제출하면 처리 중·오류 뒤 초점이 `body`로 빠졌다. 고친 뒤 같은 방식으로 다시 확인한 원본 결과.

- 수행 구분: 모의(대역 compose). `compose.yaml`·`compose.minio.yaml`·`compose.e2e.yaml`(프로젝트 `sagomungchi-e2e`, `infrastructure/stubs/e2e.env`) 스택, 웹은 `playwright.e2e.config.ts`의 Vite dev(`VITE_API_MOCK=false`)로 실제 core에 연결. 시드 관리자 `e2e-admin`
- 방법: 관리자 쓰기 요청(`POST /api/v1/admin/look-items`·`/theme-drafts`)을 브라우저 fetch에서 1초 늦춤. 단추에 초점을 둔 채 Enter로 제출하고, 0.4초 뒤(처리 중)와 오류 글이 나온 뒤 `document.activeElement`를 기록. 오류 글이 창 안에 다 들어오는지(1px 여유)도 기록
- 경우: 아이템 코드에 시드 코드 `E2E_HAT`를 넣고 저장(409 `LOOK_ITEM_CODE_DUPLICATE`), 같은 학년·주로 테마 초안을 두 번 요청한 두 번째(오류 응답, 화면 문구 "학습 서비스가 관리자 요청을 처리하지 못했습니다."). 폭 1440×900, 390×844

| 파일 | 내용 |
|---|---|
| `focus-check.spec.ts` | 확인 스크립트. `frontend/web/tests/e2e/`에 복사하고 `FOCUS_OUT`(결과 파일)을 지정해 `npx playwright test -c playwright.e2e.config.ts focus-check` |
| `focus-before.jsonl` | 고치기 전(develop `1178b4fa`) 4경우 모두 처리 중·오류 뒤 초점 `BODY`, 아이템 오류 글은 1440·390 모두 창 밖 |
| `focus-after.jsonl` | 고친 뒤 4경우 모두 처리 중에는 `aria-disabled` 단추, 오류 뒤에는 같은 단추에 초점. 오류 글은 모두 창 안 |

`during`·`after`는 초점 요소의 태그와 앞부분 글자(`[aria-disabled]`는 처리 중 표시). 학생 원문·비밀 값 없음.
