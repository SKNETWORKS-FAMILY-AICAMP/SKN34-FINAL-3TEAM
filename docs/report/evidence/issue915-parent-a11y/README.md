# #915 학부모 접근성 serious 4종 수정 뒤 실서버 재점검 (NFR-UX-02, 2026-11-23)

#885 실서버 UX 점검에서 남은 학부모·학부모 로그인 axe serious 위반(`color-contrast`·`target-size`·`aria-prohibited-attr`·`link-in-text-block`)을 고친 뒤([frontend 52](../../frontend.md#52-학부모-화면-접근성-serious-4종-수정-nfr-ux-02-915-2026-11-23)), #885와 같은 점검 스크립트로 다시 잰 결과. 판정은 [testing-ci 9.3](../../testing-ci.md#93-근거표) UX-02 줄.

## 환경

| 항목 | 값 |
|---|---|
| 수행 구분 | **모의**(대역 compose: Google·LLM·M2·설명 sLLM·토스 대역, core·learning·ai·report·DB·브로커는 실제). 오류·진행 글의 "통신 끊김·늦음"만 Playwright `page.route` 가로채기(#885와 같음) |
| 커밋 | `fix/915-parent-a11y` = develop `02a51fc3`(#885·#914·#917 병합 뒤) + #915 수정 1커밋 |
| 스택 | [testing-ci 2절](../../testing-ci.md#2-실서버-브라우저-e2e와-외부-스텁-246) 명령 그대로(`down -v` 뒤 `up --build`). 첫 기동에서 RabbitMQ가 `.erlang.cookie` 권한 오류(eacces)로 멈춰, 같은 명령으로 다시 내리고 띄움(12:23 정상 기동) |
| 날짜 | 2026-11-23(월) KST. 기준 E2E 12:23~12:29(9 passed, 5.6분), 점검 12:29~12:39(1 passed, 9.7분) |
| 도구 | Windows 11(10.0.26200), Docker 29.6.1, Node 26.3.0, Playwright 1.64.1 + Chromium, axe-core 4.10.2(npm tarball을 저장소 밖 임시 폴더에 받아 주입, sha1 `85228e3e1d8b8532a27659b332e39b7fa0e022df` — npm `dist.shasum`·#885와 같음, 의존성 추가 없음) |
| 스크립트 | [`issue885-ux-real-server/ux-audit.spec.ts`](../issue885-ux-real-server/ux-audit.spec.ts) 수정 없이 실행. `playwright.e2e.config.ts`에서 `testDir`만 그 폴더로 바꾼 임시 설정(커밋 안 함), `OUT_DIR`을 이 폴더로 지정해 #885 결과 파일은 덮어쓰지 않음 |

## 파일

| 파일 | 내용 |
|---|---|
| [axe.json](axe.json) | axe 99회(#885와 같은 화면·폭): 위반 규칙·영향도·건수·선택자, best-practice는 건수만 |
| [overflow.json](overflow.json) | 넘침 133회(UX-01 회귀 확인용) |

스크립트가 함께 쓰는 `keyboard.json`·`states.json`은 이번 수정 범위 밖이라 넣지 않았다. 합성 자녀 닉네임은 스크립트가 `<자녀>`로 바꾼다.

## 결과

| 화면(폭) | #885(수정 전) | #915(수정 후) |
|---|---|---|
| 학부모 로그인(1440·390) | `color-contrast` 각 2건(`.ux-login-or`·`small`, 4.41:1) | 0 |
| 새 보호자 온보딩(동의)(1440·390) | `target-size` 각 2건(체크박스 20×20px) | 0 |
| 자녀 추가(1440·390) | `target-size` 각 1건 | 0 |
| 학습 현황(1440) | `aria-prohibited-attr` 4건(`div.pd-recent-missions`) | 0 |
| 문의 결과(390) | `link-in-text-block` 1건(`a[href$="journal"]`) | 0 |

- 학부모 16화면·공개 2화면 1440·390(리포트 목록·주간 리포트 상세는 1440만) 34회 모두 serious·critical 0
- 전체 99회: serious·critical 0(학생 0 유지, 관리자는 #914 반영으로 0, 관리자 로그인 포함)
- best-practice(참고, 판정 밖): 학부모 `landmark-complementary-is-top-level` 2·`heading-order` 1(#885는 각 2)
- 넘침: 133회 모두 0

## 한계

- 1회 실행 기록이다. 자동 회귀는 MSW `tests/browser/accessibility.spec.ts`(카드 역할·링크 밑줄·자녀 추가 체크박스 크기)이고, 로그인 아이디 폼은 실제 모드에서만 나와 MSW 회귀에 없다
- 화면 읽기 프로그램·실기기는 쓰지 않았다(#885와 같음)
