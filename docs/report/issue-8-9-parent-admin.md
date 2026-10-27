# 이슈 #8·#9 학부모·관리자 화면

## 착수와 기준

- 2026-10-26, `develop` 66f6052에서 origin fetch(prune 없음). upstream 대비 0/0, 진행 중 Git 작업 없음. 이전 #7 로컬 변경은 보존한다.
- 사용자 요청으로 #8과 #9를 로컬 구현한다. push·PR 생성은 보류한다. 공통 기반은 아직 병합되지 않았으나 동일 작업 트리의 #7 공통 컴포넌트를 재사용하며 별도 복제하지 않는다. 향후 PR 시 공통 → 학생·학부모·관리자 순서로 분리 검토가 필요하다.
- docs/README, architecture 1.3·3장, api-spec 1.2~1.6·2.1·2.3~2.5·2.8·3.3·3.4, functional-spec 1.1·1.3·1.4·ACC/DSH/AGT/RPT/ADM, usecase 4.6, erd 3.2·3.5·4.1 기준.
- 이슈의 ‘확인 필요’ P01/P02/P06/P07/P08은 현재 확정 정책을 따른다. 특히 다른 보호자의 기존 자녀 연결은 P02에 따라 **미지원**이다. `/children/link`를 임의로 만들지 않고 신규 자녀 등록으로 안내한다.
- 미션 장면 업로드 API가 없으므로 기존 장면/정적 대체와 장면 URI 입력을 제공한다. 파일을 업로드한 척하거나 새 업로드 API를 만들지 않는다. 실제 업로드 방식은 담당자 결정 대상이다.
- API에 없는 DTO는 api-spec 3.9·3.10의 **목업 계약 초안**으로 먼저 기록한다. 실제 backend/OpenAPI 확정·서비스 통합을 의미하지 않는다.

## 구현·검증 기록

아래 완료는 **로컬 MSW 화면 구현** 기준이다. GitHub 이슈 본문 체크박스·PR 상태는 변경하지 않았다.

### #8 학부모

- [x] 가입·이용/개인정보 동의 문서 조회, 문서 ID·버전·동의 여부 전송. 관리자 권한 선택 가입 없음.
- [x] 자녀 목록·전역 전환, 자녀 없음/기록 없음 안내, 법정대리인 동의 포함 등록, 최대 3명 제한. 가상 계정 간 자녀 목록 분리.
- [x] 요약 Metric(개수·비율/null·기간·분자/분모·계산식·출처), 생각 유형별 미관찰, 학습 기록 상세의 최초/보완 답변·되묻기·도움·돌아보기.
- [x] 자녀·기간 URL 쿼리를 대시보드·분석·리포트 간 유지. 응답의 실제 기간을 별도로 표시. 자녀 변경 시 이전 자녀 결과 비노출.
- [x] 대화 생성·목록·상세, SSE status/delta/clarification/result/error/done, 확인된 범위로 후속 질문, 변경 조건 표시, 실패 메시지 전용 retry, 별도 evidence 조회.
- [x] delta는 임시 상태로만 표시하고 result로 교체. error/화면 이탈 시 폐기. 화면 이탈 시 전달한 AbortSignal 취소. 삭제된 근거 available:false/410 이용 불가, 원문 대체 없음.
- [x] 주간 목록·생성 상태 구분, 3.4 상세 필드, 근거 조회, 서버 URL 기반 PDF/Markdown 다운로드, 만료 티켓·자녀 접근 검사, 새 판 재생성과 이전 판 보존.
- [x] 무료 자녀는 분석 대화 제한·수치 리포트만 표시. 정보 수정·중요 변경 전 재확인, 단기 토큰은 메모리 보관.
- 정책상 제외: 기존 학생 타 보호자 연결은 P02 미지원. 실제 인증/동의 보관·서버 쿠키·리포트 생성/파일 저장·LLM 실행은 구현/검증하지 않았다.

### #9 관리자

- [x] GET /me.permissions의 CONTENT/SERVICE_OPS/PAYMENT_VIEW/PAYMENT_REFUND에 따른 메뉴·버튼 구분. 숨겨진 메뉴 우회 시에도 서버 목에서 403 검사.
- [x] 운영 요약의 집계 기간/기준·상태별 목록 연결, 작업 필터·상세·이력·멱등 재처리, 실패는 FAILED 유지. 큐/DLQ·감사 이력.
- [x] 미션 상태별 건수·학년/유형 필터·작성/수정, 새 미션/기준표 버전과 이력. 요소·배점·흔한 오답·정답/예시·좋은 생각·힌트·금지어 입력.
- [x] 학생 MissionScene/AnswerFields 재사용 미리보기, 검토 요청 → 현재 버전 검토 → 게시, 422 missingFields 표시, 제공 중단. 게시본 변경/중단 시 이미 시작한 시도는 당시 문항 유지.
- [x] 모델/프롬프트 평가 근거 등록·승인 버전 활성화/되돌리기·재분석 여부 이력, 사용량의 미측정 토큰/비용 구분.
- [x] SERVICE_OPS의 신고 상세 열람(명시적으로 연결된 가상 시도만·열람 감사), 검토·원본 답변을 보존하는 정정 이력과 영향 확인 대기 표시.
- 미지원: 장면 업로드 API(URI/기본 장면만). 실제 모델 평가 승인·배포 이벤트·재처리 큐 실행·정정의 대화/집계/리포트 반영은 백엔드 통합 대상. 결제 운영은 범위 밖.

## 검증과 재현

- 실행: frontend/web에서 `npm test`, `npm run lint`, `VITE_API_MOCK=true npm run build`, `node tests/production-mocks.mjs`.
- 단위/어댑터 40개 통과. lint 경고/오류 없음, build 통과. 운영 빌드에 MSW·학생/학부모/관리자 fixture·개발 worker 미포함 확인(환경 변수가 true여도 DEV gate로 제외).
- 브라우저: `tests/parent-admin-browser.mjs`(학부모/관리자), `tests/student-browser.mjs`(학생 회귀). Playwright/Chrome 경로와 DEV 서버 주소는 frontend/web/README 참고.
- 실제 API 모드: `tests/api-mode-browser.mjs`, 별도 preview 5174에서 서비스워커·상태 시연 UI 없음, `/api/v1/auth/refresh`·`/auth/login` 요청과 404 오류 표시/예시 자동 대체 없음 확인. 응답은 404 스텁이므로 core 정상 연동 성공이 아니다.
- 학생 회귀 18개 통과, pageerror 0. 좁은 390×500 뷰포트의 제출 버튼 sticky/정적 장면 확인. 실제 모바일 키보드·실기기 검증 아님.
- 최종 학생 회귀 결과: `C:/Users/playdata2/outputs/issue8-9-20261026/student-verified/results.json`. 전체 단위 40·역할별 브라우저 43(학생 18+학부모/관리자 25) 통과, 최종 lint/build/운영 목 제외 검사도 재실행하여 통과했다.
- 학부모/관리자 종합 브라우저 최종 결과는 아래 후속 기록 참조. 외부 웹폰트 지연과 독립적인 검증을 위해 이 스크립트는 Google Fonts 요청을 차단하고 시스템 대체 글꼴로 실행한다.
- 원격 CI·배포·실제 backend/쿠키/DB/AI/PG 통합 테스트 미수행.

## 남은 확인·반영

최종 학부모/관리자 Chromium 검증 25개 통과, pageerror 0. 관찰된 `/api/v1` 응답 342건 모두 `fromServiceWorker()` 확인. 근거 JSON/새 JPEG는 `C:/Users/playdata2/outputs/issue8-9-20261026/verified/`에 기록했다. 분석 중 자녀 변경 시 fetch에 전달한 signal의 abort 이벤트까지 확인했으며, 실제 core→AI 취소 전파 검증을 뜻하지 않는다.

- [ ] api-spec 3.8~3.10 목업 DTO의 담당자 확인. 선택적 작업 기간 필터·동의/프로필·대화 이력/clarification·운영 응답 형태를 실제 Controller/OpenAPI에 맞춰야 한다. 현재 저장소에 contracts/openapi 디렉터리는 없으며 미승인 DTO를 정식 서버 계약으로 생성하지 않았다.
- [ ] 실제 서버로 목 OFF 통합 검증, 파일/권한/변경 이력/정정 영향 반영 검증.
- [ ] 장면 파일 업로드 방식 결정.
- [ ] 공통/학생/학부모/관리자 변경을 검토 가능한 커밋·브랜치로 분리. 현재 로컬 feature/fe-parent에 기존 #7 변경까지 보존 중. 커밋·push·PR은 사용자 요청으로 보류.
