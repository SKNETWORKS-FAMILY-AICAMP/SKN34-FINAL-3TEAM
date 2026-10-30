# Learning 연동 변경 인수인계 (2026-10-29)

현재 브랜치: `feature/admin-screen-completion`. PR 생성·push는 사용자 요청으로 중단했습니다. 이전 관리자 화면 작업 커밋은 로컬에 보존했고, 아래 변경은 작업 트리에 있습니다.

## 합의 요청에 대한 프론트 반영

- D1 동의: 정답 키는 입력 방식별 객체입니다. 고르기 `choiceIds`, 순서는 정답 순서의 `choiceIds`, 분류는 모든 항목의 `assignments`, 풀이 단계는 수만 담는 `finalAnswer`. 서술·논술은 `answerKey:null`과 예시 답을 보냅니다. 관리자 화면은 직접 객체 문자열을 쓰지 않고 선택·순서·분류·수 입력으로 객체를 구성합니다.
- D2 동의: `missingFields`는 영문 코드를 유지합니다. 관리자 미션 화면에서 알려 주신 코드와 인덱스가 있는 `rubric.elements[0].points` 등을 한글로 표시합니다. 알 수 없는 코드는 원래 코드를 남깁니다. 공통 오류 표시 부품은 수정하지 않았습니다.
- D4 동의: 공개 중 내용·기준표 수정과 검토 요청·검토는 공개 상태와 기존 `publishedVersion`을 유지합니다. 재게시 성공 후에만 공개본을 바꿉니다. 화면에서 편집본·기준표 버전과 학생 공개본을 구분합니다. DEV 목업도 같은 흐름이며 진행 중 시도는 원래 스냅샷을 유지합니다.
- D3: 모든 입력 방식에 요소 1개 이상. 풀이 단계는 `FINAL_ANSWER` 외 요소가 필요하고 다른 입력 방식에서는 이 코드를 허용하지 않습니다. 요소 이름·양의 배점을 검사합니다.
- D5: 미션 쓰기에 `answerUnit`·문자열 배열 `inputTemplate`을 추가했습니다. DB에 없는 `scene`과 응답 전용 `version/createdAt`을 전송하지 않고 `sceneUri/staticSceneUri`만 보냅니다. 업로드 기능은 추가하지 않았습니다.
- D6: 전체 상태별 counts와 필터 목록을 분리하고 페이지 이동을 추가했습니다. 검토 요청/검토는 현재 버전 쌍, 게시/중단은 `{}`, 성공은 전체 AdminMission을 사용합니다.

## 학생 화면

- 돌아보기: 화면 문구는 한글, 활성 학습 경로의 요청은 `EASY/NORMAL/HARD`로 보냅니다.
- 자기 평가: 마무리 뒤·완료 전에만 표시합니다. `{checks:[{elementId,checked}]}` 일부 저장·false 변경을 허용하고 응답 전체의 `selfChecked/aiChecked/quote`를 나란히 표시합니다. FINAL_ANSWER를 포함해 서버에서 준 요소를 생략하지 않습니다. 저장 중 돌아보기 완료와 경합하지 않도록 막습니다.
- 풀이 답 뒤에 `answerUnit`을 고정 표시합니다. 사용자는 수를 입력하고 단위를 요청 값에 자동 결합하지 않습니다.
- 분류 그룹은 서버 categories의 label을 사용합니다. 풀이·논술 입력 틀 이름은 서버 inputTemplate을 사용하며 답을 미리 채우지 않습니다.

## #82 담당 파일 경계

직접 수정하지 않은 파일:
- `src/domain/classroom.ts`
- `src/data/classroom/apiGateway.ts`
- `src/data/classroom/demoGateway.ts`
- `src/presentation/shared/ClassroomParts.tsx` (공통 오류 표시)

충돌을 줄이기 위해 `domain/learning.ts`에 Mission 확장 메타데이터를, `data/classroom/learningApi.ts`에 돌아보기 코드 변환·자기 평가 API를 분리했습니다. 현재 `useClassroom.ts`의 학습 액션이 이 경로를 사용합니다. #82 병합 후 공통 Mission 타입에 answerUnit/inputTemplate을 통합할 수 있습니다. apiGateway.reflect의 기존 구현은 이번에 직접 수정하지 않았고 활성 UI에서는 호출하지 않습니다. 후속 담당자가 공통 게이트웨이에 통합할 때 중복을 정리해야 합니다.

A3 신고는 확정 대기: 현재 answerId를 JUDGMENT ID로 보내는 기존 로직을 이번에 임의 수정하지 않았습니다. #146/core가 판정 ID 제공 위치를 확정한 뒤 연결해야 합니다. B의 null·versions·retryable·되묻기 조건 변경은 #82 담당 범위 그대로 남겼습니다.

## 검증 및 한계

- 단위·계약 테스트 119개 통과. 신규 5개는 난이도 코드, 자기 평가 부분 갱신·시점 제한, 정답/요소 조건, 쓰기 요청 필드, 공개본 유지/재게시를 검증합니다.
- 운영 빌드 및 DEV 화면의 브라우저 검증은 API 대역/가상 데이터입니다. 실제 learning/core 서버·DB 통합 성공을 뜻하지 않습니다.
- learning #145 응답 예시를 받으면 타입·상태 전이·실제 게시 검증을 추가 확인해야 합니다.
- 화면설계서 10쪽과 생성 소스의 꾸미기 정책을 “보상이나 유료 결제 아이템으로 반영할지 추후 회의 후에 결정할 예정입니다.”로 교체했습니다. 보상·결제 기능 자체는 추가하지 않았습니다.

최종 브라우저 검증: 학생 답 단위/입력 틀, 자기 평가 및 돌아보기 완료, 관리자 미션 생성→검토→게시→공개 중 v2 수정까지 통과했습니다. 1440·1024·768px의 3개 화면 × 3개 규격(9조합)에서 가로 넘침·브라우저 실행 오류가 없었습니다. 캡처·결과는 `C:/Users/playdata2/outputs/learning-alignment-20261029-ready/`에 있습니다. 최종 테스트 119개·lint·운영 빌드·운영 목업 제외 검사·git diff --check 통과. JS 청크 500kB 초과 경고는 남아 있습니다. PDF는 기존본과 46쪽 렌더를 대조해 10쪽만 변경됐음을 확인했습니다.
