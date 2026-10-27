# 학생·학부모 로그인 분리 (P01 개정)

작성일: 2026-10-27. 기준: `develop`의 `e91bc20`, [기능 명세 P01](../design/functional-spec.md#14-확정-정책), [API 명세 3.11](../design/api-spec.md#311-학생-기기-등록pin-로그인-p01-개정), [ERD 10장](../design/erd.md#10-p01-개정-학생-기기pin-변경-예정-미적용).

설계 문서 개정만 포함한다. core 인증·Flyway 마이그레이션·프론트 화면·MSW 핸들러는 후속 작업이다.

## 배경

기존 P01은 학생 별도 계정 없이 학부모 로그인 → 자녀 선택 → `POST /auth/student-sessions`로 학생 세션을 발급했다. 학부모가 매번 옆에서 로그인해야 하므로 학부모 부재 시 자녀 단독 학습이 불가능하다. 자녀가 혼자 학습하고 학부모는 이후 리포트로 확인하는 구조로 바꾼다.

## 타 서비스 사례

| 서비스 | 자녀 진입 | 학부모 역할 |
|---|---|---|
| [Khan Academy](https://support.khanacademy.org/hc/en-us/articles/202487460-If-my-child-is-under-age-13-what-login-options-are-there-) | 학부모가 만든 자녀 전용 아이디·비밀번호(이메일 불필요) | 비밀번호 관리·변경 |
| [Seesaw](https://help.seesaw.me/hc/en-us/articles/4424230271501-Seesaw-Codes) | 학생별 16자리 코드·QR, 1년 유효, 유출 시 재발급 | 별도 가족 연결로 열람 |
| [ClassDojo](https://help.classdojo.com/hc/en-us/articles/360009869032-How-Students-can-Log-into-ClassDojo-at-Home) | 학부모 계정에서 전환 또는 학부모 앱의 개별 QR로 다른 기기 로그인 | QR 발급 |
| [Epic](https://support.getepic.com/hc/en-us/articles/360027225131-How-do-I-add-edit-my-child-s-profile-PIN) | 학부모 계정 하위 프로필 + 선택적 4자리 PIN(연속 숫자 비권장) | 학부모 영역 진입 시 비밀번호 재입력 |
| [Google Family Link](https://support.google.com/families/answer/7158477) | 자녀 계정을 기기에 추가할 때 학부모 로그인으로 승인 | 원격 관리 |
| [아이스크림 홈런](https://apps.apple.com/kr/app/id766231881) | 학생 학습 앱 분리 | 학부모 앱에서 학습 시작·종료·현황 확인 |

공통 패턴: 최초 1회 학부모 승인(기기·코드) → 이후 자녀는 쉬운 수단(PIN·QR·프로필)으로 진입 → 학부모 영역은 재인증으로 보호.

## 대안 비교와 결정

| 방식 | 판단 |
|---|---|
| 자녀 아이디·비밀번호 | 초3~6이 관리하기 어렵고 유출 시 어느 기기에서나 사용 가능. 자녀 식별 정보 추가 수집 부담 → 비채택 |
| QR·코드 단독 | 코드 자체가 소지형 자격증명이라 종이·사진 유출에 취약 → 기기 등록 수단으로만 사용 |
| PIN 단독 | 4~6자리는 추측 공격에 약함 → 비채택 |
| **학부모 승인 기기 등록 + 자녀 PIN** | 기기(소지)와 PIN(지식) 2요소. 자녀가 이메일·OTP를 관리하지 않음 → **채택** |

## 확정 동작

- 진입 경로 두 가지
  - 단독: 학부모가 등록한 기기에서 자녀 프로필 선택 + PIN
  - 동석: 기존 `POST /auth/student-sessions` 유지
- 기기 등록
  - 학부모가 1회용 페어링 코드(8자리, 10분, 1회) 발급
  - 자녀 기기에서 입력·QR 스캔 → 기기 자격증명 httpOnly 쿠키 발급
  - 기기 하나에 자녀 여러 명 등록 가능(형제 공용 태블릿)
- 기기 관리: 등록 90일 후 만료(설정값). 학부모가 목록 조회·해제
- PIN
  - 숫자 4~6자리, 동일 숫자 반복·연속 숫자 거부
  - 설정·변경은 재확인(`X-Reauth-Token`) 필요
  - 연속 5회 실패 시 잠금, 학부모가 재설정해야 해제
- 미등록·해제·만료 기기에서는 PIN이 맞아도 거부
- 학생 세션
  - refresh 미발급, access 만료 시 PIN 재입력(초안은 자동 저장)
  - 권한은 동석 경로와 동일. 학부모 화면·리포트·자녀 관리 접근 불가
- 기기 등록·해제·PIN 설정은 `audit_log` 기록
- 자녀 이메일·전화 미수집. PIN·기기 자격증명은 해시만 저장

## API 변경

| Method | Path | 역할 | 변경 |
|---|---|---|---|
| POST | `/student-devices/pairings` | 학부모 | 신규. `{childIds[]}` → `{pairingCode, expiresAt}` |
| GET | `/student-devices` | 학부모 | 신규. 등록 기기 목록 |
| DELETE | `/student-devices/{deviceId}` | 학부모 | 신규. 기기 해제 |
| PUT | `/children/{childId}/pin` | 학부모 | 신규. PIN 설정·잠금 해제 |
| POST | `/auth/student/devices` | 공개 | 신규. 페어링 코드로 기기 등록, 쿠키 발급 |
| GET | `/auth/student/profiles` | 기기 쿠키 | 신규. 기기에 등록된 자녀 프로필 |
| POST | `/auth/student/login` | 기기 쿠키 | 신규. `{childId, pin}` → `STUDENT` 토큰 |
| POST | `/auth/student-sessions` | 학부모 | 유지. 동석 경로로 설명만 변경 |
| POST | `/auth/login` | 공개 | 유지. 학생 단독 진입은 3.11 안내로 문구 변경 |

- 신규 오류 코드
  - 기기·자녀 무효: `401 STUDENT_DEVICE_INVALID`
  - PIN 관련: `401 STUDENT_PIN_INVALID`(`remainingAttempts`), `423 STUDENT_PIN_LOCKED`, `409 STUDENT_PIN_NOT_SET`
  - 페어링 코드 무효: `400 PAIRING_CODE_INVALID`
- 학생 기기 API를 `/auth/student/*` 아래에 둔 이유: 기기 쿠키 path를 `/api/v1/auth/student`로 제한해 다른 API 요청에 쿠키가 실리지 않게 함

## DB 변경 (예정)

ERD 10장에 표로 기록했다. CI 스키마 대조(`scripts/verify_db_schema.py`)는 ERD 3~5장 Mermaid를 실제 DB와 비교하므로, 마이그레이션 전에는 3.1 Mermaid를 바꾸지 않았다. 개정 후에도 ERD 계약(테이블·컬럼·CHECK·인덱스)이 HEAD와 같음을 확인했다.

- `student`에 `pin_hash`, `pin_failed_count`, `pin_locked_at`, `pin_updated_at` 추가
- `student_device`(학부모 소유 기기, `token_hash` UK, 만료·해제 시각), `student_device_child`(기기별 로그인 가능 자녀) 신설
- 페어링 코드는 Redis 저장, 테이블 없음
- 후속 core Flyway V8에서 3.1 Mermaid·6장 인덱스로 옮긴다

## 변경 문서

- `functional-spec.md`
  - P01 개정
  - FN-ACC-01·05 수정, FN-ACC-14 신설
  - 1.1 권한 표에 학생 기기·PIN 행 추가, NFR-SEC-08 신설
- `api-spec.md`
  - 1.2 기기 자격증명, 1.3 오류 코드, 2.1 목록 추가
  - 3.7 `/auth/login` 문구 수정, 3.11 신설
- `erd.md`: 1장 학생 계정 문구, 10장 신설
- `class-diagram.md` 3.1: `StudentDeviceController`, `StudentAuthService`, `StudentDevice`, `StudentDeviceRepository` 추가, `Student` PIN 메서드 추가
- `sequence-diagram.md` 2.4: 기기 등록·PIN 로그인 다이어그램 추가

## 후속·미확정

- core: `StudentAuthService`·쿠키 처리·시도 제한, Flyway V8, OpenAPI 반영
- 프론트
  - 학부모: 기기 등록·PIN 설정·기기 목록 화면
  - 자녀 기기: 프로필 선택·PIN 입력 화면
  - MSW 핸들러
- PIN 잠금·새 기기 등록 시 학부모 알림: `notification.type` CHECK 추가가 필요해 알림 기능과 함께 확정
- 학생 access token TTL, 기기 만료 기간(90일), 실패 허용 횟수(5회)는 설정값으로 두고 구현 시 확정
- 기기 해제 직후에도 이미 발급된 학생 access token은 만료까지 유효. 즉시 차단이 필요하면 토큰 폐기 목록 도입을 별도 검토
