# #549 M2 글 정리·경계 적용

## 확정 범위

11/12 c판과 담당자 후속 답변을 적용한다. 논술 3.1·서술 3.0 단독 모델을 유지하며 8:2 혼합은 미채택으로 제외한다.
논술은 칸 이름 → 지시문 복사 → 반복 제거 순서로 정리하고 100자 미만은 채점하지 않는다.
서술은 복사 → 반복 제거 후 공백 제외 10자 미만은 채점하지 않고, 10~99자는 채점하며 짧은 답 안내를 준다.
두 유형 모두 512토큰을 넘으면 앞+끝을 읽는다. 서술 content3 선택 보정은 정리한 글을 사용한다.
학습 가중치·승인 학년·활성화 설정·제출 원문·생각 판정은 변경하지 않는다.

## 응답 계약

미활성은 기존 `active:false`. 활성 모델에서 길이 미달이면 `active:true, scored:false, reason:TEXT_TOO_SHORT`이며 scores/rawScores가 없다.
정상 점수와 길이 미달 응답 모두 preparation에 copied/repeated/chars/labelsRemoved/short/truncated/notices/ruleVersion을 둔다.
AI는 점수 없는 응답을 m2=null, m2Preparation에 저장한다. 평균·불일치와 리포트 설명 후보에서 제외한다.
learning은 미션 inputTemplate의 네 칸 이름을 essayLabels로 전달한다. 학생 피드백에는 허용 목록으로 변환한 m2Notices 문구만 노출한다.

## 검증

구현 및 실제 모델 검증 결과는 완료 후 기록한다.
