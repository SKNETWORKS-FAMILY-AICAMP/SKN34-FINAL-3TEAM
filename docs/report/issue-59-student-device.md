# #59 학생 PIN 로그인·학부모 기기 관리 화면 (MSW 목업)

작성일: 2026-10-27. 기준: `develop`의 `ecd6ecf`(#61 Google 로그인 병합 후), [API 명세 3.11](../design/api-spec.md#311-학생-기기-등록pin-로그인-p01-개정), [로그인 분리 설계](student-login-separation.md).

프론트 화면과 MSW 목업만 포함한다. core 인증·Flyway·실제 httpOnly 쿠키 연동은 범위 밖이다.

## 구현

| 화면·경로 | 내용 |
|---|---|
| `/student/login` (`DeviceLogin`) | 미등록 기기: 등록 코드·기기 이름 입력만 표시(PIN 화면 없음). `?code=`로 QR 링크에서 코드 자동 입력. 등록 기기: 프로필 선택 → 화면 숫자 키패드 PIN |
| 학생 access 만료 | #61 정책대로 학생 세션은 refresh 없이 `/student/login`으로 보낸다. PIN을 다시 넣으면 보던 학생 화면으로 돌아가고 초안은 서버 저장분으로 이어진다 |
| `/parent/devices` (`StudentDevices`) | 본인 재확인 후 자녀별 PIN 설정·재설정(잠금 해제), 자녀 선택 → 페어링 코드·남은 시간·QR, 등록 기기 목록(이름·자녀·마지막 사용·만료)과 해제 |
| 로그인 화면 | "자녀 기기로 시작하기 (PIN)" 진입 추가. 학생 → 학부모 전환은 학부모 로그인 요구 |

- `domain/studentDevice.ts`: PIN 규칙(숫자 4~6자리, 같은 숫자 반복·1씩 오르내리는 연속 거부), 코드 정리·표시, 남은 시간, 오류 코드 → 아이용 안내 상태.
- `data/studentDevice/`: 3.11 엔드포인트 어댑터와 Query 훅. PIN 로그인 응답의 역할·자녀·학년(3~6)을 검사하고 access token은 메모리에만 둔다. 세션에 `entry: 'DEVICE' | 'GUARDIAN'`을 표시한다.
- 오류 안내: `STUDENT_PIN_INVALID`(남은 기회 표시), `STUDENT_PIN_LOCKED`(키패드 숨김·보호자 재설정 안내), `STUDENT_PIN_NOT_SET`(보호자 동석 로그인 안내), `STUDENT_DEVICE_INVALID`(다시 등록 화면), `CHILD_NOT_LINKED`, `PAIRING_CODE_INVALID`.

## 결정

- QR: 화면 표시만 추가. 자녀 기기의 카메라 스캔 기능은 만들지 않았고, QR은 `/student/login?code=…` 링크다. 생성에 `qrcode` 패키지를 추가했다(클라이언트 생성, 서버 호출 없음).
- 기기에 자녀가 1명이면 프로필 선택을 건너뛰고 바로 PIN 화면을 연다("내가 아니에요"로 되돌림).
- PIN 입력은 화면 숫자 키패드(키 72px, 4~6자리 점 표시). 물리 키보드 숫자·Backspace·Enter도 받는다.
- 자녀 기기에서 보호자 계정으로 로그인하지 않도록 코드 발급 화면에 안내한다.

## API 명세 변경

- `GET /children` 응답에 `pinSet`·`pinLocked`를 추가했다(학부모 화면의 PIN 상태 표시용). PIN·해시·실패 횟수는 노출하지 않는다. 백엔드 확인 필요.

## 개발용 기기 상태

MSW는 httpOnly 쿠키를 만들 수 없어, 기기 쿠키 대신 `sessionStorage`의 `sagomungchi:msw-device:v1`에 현재 기기 ID·PIN 해시·기기·페어링을 둔다. DEV+MSW에서만 "기기 상태 시연" 선택기(해제·만료·잠김·PIN 미설정·초기화)가 보인다. 운영 번들에 포함되지 않는지 `tests/production-mocks.mjs`가 검사한다.

## 검증

| 항목 | 결과 |
|---|---|
| `npm test` | 58건 통과 (`studentDevice.test.ts`, `studentDeviceMock.test.ts` 포함) |
| `npm run lint`, `npm run build`, `node tests/production-mocks.mjs` | 통과 |
| `tests/student-device-browser.mjs` (신규) | 9건 통과: 미등록 기기 PIN 화면 미노출, 학부모 등록 → PIN → 학생 홈 → 미션 작성 시작, 프로필 선택·PIN 미설정 안내, 5회 실패 잠금·학부모 화면 잠김 표시, 만료 후 새로고침, 미션 중 만료 → PIN → 같은 미션·초안 유지, 학생 → 학부모 로그인 요구, 해제 기기 재등록 화면, 기기 목록 해제 |
| `tests/student-browser.mjs` | 23건 통과. #61의 학생 재로그인 정책(새로고침·만료 시 `/student/login`)에 맞춰 진입·새로고침 복원·만료 사례의 기대값을 고침 |
| `tests/parent-admin-browser.mjs` | develop `ecd6ecf` 병합 후 두 번째 사례(신규 가입 연속 흐름)의 로그인 칸 대기에서 실패. develop 단독에서도 같은 위치에서 실패하는 #61 가입 흐름 변경 영향이라 이 PR에서 고치지 않음. 병합 전에는 22건 통과 후 "작업 재처리"에서 실패(병합 전 HEAD도 동일) |
| `tests/browser-smoke.mjs` | `주간 리포트` 버튼 대기 실패. README에 기록된 대로 #7 초기 화면용 기록이며 HEAD에서도 동일 |

## develop(#61) 병합 반영

- #61이 둔 `/student/login` 자리 화면(`StudentEntryPage`, "기기·PIN은 후속")을 이 기기·PIN 로그인으로 바꾸고 `/student-login` 경로는 없앴다.
- 학생 토큰 만료 시 화면 안 PIN 재입력 창은 빼고 #61의 학생 재로그인 흐름을 따른다. 대신 로그인 전 경로를 기억해 PIN 뒤 돌아간다(토큰·입력 원문은 저장하지 않음).
- `/auth/student/*`(기기 등록·프로필·PIN 로그인)의 401은 로그인 단계 오류라 apiClient가 학생 재로그인 신호로 바꾸지 않게 했다.
- PIN 로그인 성공 시 #61 방식대로 학생 역할 토큰으로 두고 다른 탭에 알린다.

## 미확정

- PIN 연속 숫자의 순환(`90123` 등) 처리: 명세에 정의가 없어 거부하지 않는다.
- 실제 기기 쿠키(`student_device`, path `/api/v1/auth/student`)·서버 잠금·만료 처리는 백엔드 통합 때 확인해야 한다.
- 학부모 화면의 PIN 재확인 토큰 유효 시간(5분 안내)은 기존 `/me/reauth` 목업 기준이다.
