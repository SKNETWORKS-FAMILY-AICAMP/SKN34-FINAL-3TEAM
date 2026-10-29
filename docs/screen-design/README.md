# 사고뭉치 화면설계서

작성: 김재현 · 2026-10-29

[화면설계서 v2.1](../outputs/사고뭉치_화면설계서_v2.1_20261029.pdf)는 표지 1장과 화면 45장(공통 4·학생 14·학부모 16·관리자 11), 모두 46쪽이다. 참고 양식 `[모델 배포]화면설계서.pdf`와 같은 배치를 따랐다.

- 상단 표: 화면명·요구사항 ID / 화면 경로·화면 ID
- 왼쪽: 화면 캡처와 파란 번호
- 오른쪽: Description(번호별 설명, 화면의 번호와 1:1)과 Check Point

v2.1은 학생 로그인 화면의 테마 문구를 뺀 캡처를 반영했다. v2.0도 같은 폴더에 남겨 두었다. 이전 판 v1.1(46쪽, 다른 배치)은 `SKN34-FINAL-3TEAM-admin-ui` 작업본의 `docs/outputs/`에 그대로 있다.

## 캡처 기준

| 화면 | 출처 |
|---|---|
| 공통·학생·학부모 | 이 작업본(`feature/fe-requirements-completion`)을 일반 MSW 목업 모드로 실행해 캡처. 학생 화면 로고 제거(로그인은 문구까지 제거), 고객센터·알림·계정 관리 같은 요구사항 보완 화면 포함 |
| 학생 진입 | 이 작업본의 PIN 재확인은 Google 팝업이라 자동 캡처에서 PIN을 정할 수 없다. 가상 학생 + 임시 PIN 5090 체험 경로로 실제 키패드·PIN 검사를 거쳐 진입했다 |
| 관리자 | 흑백 관리자 UI(`feature/admin-monochrome`) 작업본의 v1.1 캡처. 그 작업본은 캡처 뒤 화면 코드가 바뀌지 않았다 |
| API 모드 로그인 | v1.1 캡처(운영 빌드 + 인증 API 대역). 실제 Google 인증 완료 화면이 아니다 |

모델·AI 사용량 관리자 화면은 core 확정 계약(#93)이 이 작업본에는 반영됐지만 흑백 관리자 화면에는 아직 합쳐지지 않았다. 각 쪽 Check Point에 적었다.

## 요구사항 ID

지어내지 않는다. 기존 화면은 v1.1의 연계 기능(FN)을 `docs/design/functional-spec.md`의 요구사항 열로 바꾸고, 새 화면은 요구사항 대조 데이터(`frontend/web/src/requirements-audit.json`)에서 확인한 16개 ID만 쓴다.

## 다시 만들기

- `screens_v2.py`: 화면별 제목·경로·설명·Check Point·번호 위치. 실행하면 `2026-10-29-v2.0/screens.json`을 만든다.
- `build_template_pdf.py`: 양식 배치로 PDF 생성. 번호 수와 설명 수가 다르거나 오른쪽 칸이 넘치면 실패한다. 기존 PDF는 덮어쓰지 않는다.
- `2026-10-29-v2.0/captures/`: `run1`(공통·학생·학부모), `extra`(새 서비스 화면), `admin`, `api`.

```powershell
# 저장소 루트. reportlab·Pillow가 있는 Python과 Windows 맑은 고딕 필요
python docs/screen-design/screens_v2.py docs/screen-design/2026-10-29-v2.0/screens.json
python docs/screen-design/build_template_pdf.py --data-dir docs/screen-design/2026-10-29-v2.0 `
  --spec docs/design/functional-spec.md `
  --v11-screens ..\SKN34-FINAL-3TEAM-admin-ui\docs\screen-design\2026-10-28-v1.1\screens.json `
  --logo docs/screen-design/2026-10-29-v2.0/logo-bulb.png `
  --output docs/outputs/사고뭉치_화면설계서_새버전.pdf
```

## 검증

- 46쪽 전체를 이미지로 렌더링해 번호 위치·설명·오른쪽 칸 넘침을 확인했다.
- 캡처 33장은 레이아웃 검사 오류가 없었다. 학생 홈 1장만 경고 2건이 있었고, 화면 아래쪽 섬 지도가 잘리는 것으로 기존과 같다.
- 캡처 중 외부 글꼴(Google Fonts) 요청을 막아 손글씨 제목은 기본 글꼴로 나온다.
