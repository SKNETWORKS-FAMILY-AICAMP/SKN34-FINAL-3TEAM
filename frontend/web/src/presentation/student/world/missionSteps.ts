import type { Feedback, Reflection } from '../../../domain/classroom.ts'

/** 미션 안내 화면의 단계 칩(시안 MissionGuide·#589). 문제 푸는 화면(StudentWorkPage)은 단계 칩을 뺐다(#807 D안, 사용자 결정 2026-11-23) */
export const STEPS = ['질문 읽기', '답변 쓰기', '피드백', '마무리', '돌아보기']

/**
 * 학생에게 보이는 피드백 한 줄(문제 푸는 화면 피드백 상자 제목). 내 공책 기록 상세도 같은 말을 써서
 * 처리 상태·판정 코드(DONE·HELD 등)를 학생 화면에 그대로 내보이지 않는다(#648 시안 JournalDetail).
 * 다시 생각 판정은 '다시 생각해 볼까요?'(사용자 결정 2026-11-23 #807): 예전 '한 번 더 살펴볼까요?'는 분석하기 문제에서
 * 생각 유형 '꼼꼼히 살펴보기'·되묻기 '다시 살펴보기'와 한 화면에 '살펴보기'가 세 번 나와 헷갈렸다
 */
export function feedbackHeadline(f: Feedback) {
  return f.status === 'DONE'
    ? f.judgment?.result === 'HELD'
      ? '답을 잘 받았어요.'
      : f.judgment?.result === 'CORRECT'
        ? '정답을 확인했어요.'
        : '다시 생각해 볼까요?'
    : f.status === 'FAILED'
      ? '답은 저장했어요. 피드백은 잠시 뒤에 다시 볼 수 있어요.'
      : '답을 저장했어요. 피드백을 준비하고 있어요.'
}

/** 되묻기 종류 이름 */
export function followupLabel(type: string) {
  return type === 'ONE_STEP_MORE' ? '한 걸음 더' : type === 'LOOK_AGAIN' ? '다시 살펴보기' : '더 말해 보기'
}

/** 돌아보기 난이도를 학생 말로(돌아보기 버튼과 같은 말) */
export const difficultyLabel = (d: Reflection['difficulty']) =>
  d === '보통' ? '보통이에요' : d === '쉬웠어' ? '쉬웠어요' : '어려웠어요'
