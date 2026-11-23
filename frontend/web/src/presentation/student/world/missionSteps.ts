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

/**
 * 피드백 대기 표시(#847): 경과 시간에 따른 말풍선 문구와 캐릭터 움직임. 실제 진행과 무관한 시간표다
 * (피드백 SSE는 status(RUNNING) 한 번뿐이라 진행 정보가 없음, api-spec 3.2). 막대·퍼센트는 쓰지 않는다.
 * 움직임은 단계마다 하나: look 돋보기로 살피기, notebook 공책 넘기기(돋보기는 내려놓음), tilt 고개 갸웃, stretch 기지개(몸 전체를 쭉 폈다 쉼, 뭉치는 팔이 없는 캐릭터라 팔은 그리지 않음).
 */
export type WaitingMotion = 'look' | 'notebook' | 'tilt' | 'stretch'
export const WAITING_STEPS: readonly { from: number; line: string; motion: WaitingMotion }[] = [
  { from: 0, line: '답을 꼼꼼히 읽고 있어', motion: 'look' },
  { from: 5, line: '생각의 단서를 찾는 중이야', motion: 'notebook' },
  { from: 15, line: '너에게 할 질문을 고르고 있어', motion: 'tilt' },
  { from: 30, line: '조금 오래 걸리네. 답은 벌써 저장했어!', motion: 'stretch' },
  { from: 60, line: '거의 다 왔어. 잠깐만 기다려 줘', motion: 'stretch' },
]
/**
 * 대기 중 피드백 상자 제목(사용자 결정 2026-11-23). 말풍선이 "답을 꼼꼼히 읽고 있어"라고 해서 저장 안내와 겹치므로 지금 하는 일만 말한다.
 * 내 공책 기록 상세는 지난 기록을 보는 화면이라 feedbackHeadline의 처리 중 문장을 그대로 쓴다
 */
export const WAITING_HEADLINE = '피드백을 만드는 중이에요'
/** core→learning 피드백 시간 제한(P12·api-spec 3.2). 이보다 길게 셀 일은 없어 경과 시간을 여기서 자른다 */
export const FEEDBACK_WAIT_LIMIT_SECONDS = 80
const clampWait = (seconds: number) =>
  Number.isNaN(seconds) ? 0 : Math.min(FEEDBACK_WAIT_LIMIT_SECONDS, Math.max(0, seconds))
/** 경과 초 → 단계. next는 다음 단계까지 남은 초(마지막 단계면 null). 음수·80초 넘음·NaN은 0~80으로 자른다 */
export function waitingStep(seconds: number) {
  const s = clampWait(seconds)
  const index = WAITING_STEPS.findLastIndex((step) => step.from <= s)
  const following = WAITING_STEPS[index + 1]
  return { index, ...WAITING_STEPS[index], next: following ? following.from - s : null }
}
/**
 * 새로고침 뒤 PENDING·RUNNING을 이어받을 때의 대기 시작 시각(밀리초). 마지막 답의 submittedAt부터 세되
 * 기기 시계가 서버와 어긋날 수 있어 경과를 0~80초로 자른다(미래 시각이면 지금부터, 너무 오래면 80초 전).
 */
export function resumeWaitStart(submittedAt: string | undefined, now: number) {
  const at = submittedAt ? Date.parse(submittedAt) : Number.NaN
  return Number.isNaN(at) ? now : now - clampWait((now - at) / 1000) * 1000
}

/** 되묻기 종류 이름 */
export function followupLabel(type: string) {
  return type === 'ONE_STEP_MORE' ? '한 걸음 더' : type === 'LOOK_AGAIN' ? '다시 살펴보기' : '더 말해 보기'
}

/** 돌아보기 난이도를 학생 말로(돌아보기 버튼과 같은 말) */
export const difficultyLabel = (d: Reflection['difficulty']) =>
  d === '보통' ? '보통이에요' : d === '쉬웠어' ? '쉬웠어요' : '어려웠어요'
