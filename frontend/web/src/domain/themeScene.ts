/**
 * 테마 시도의 오늘 장면(learning #438 `ThemeScene`, api-spec 3장 "시도 시작·이어하기 응답 themeScene", 웹 #807).
 * learning은 그 시도 테마 게시본의 그 미션 요일 값을 그대로 주고 EXTRA는 null이다. 웹은 대화만 쓰고
 * hintSpots(생각 열기 표시 위치, ai 테마는 null)는 읽지 않는다. 살펴보기 물건은 미션 `sceneMotion.spots`(domain/themeMotion.ts)에 있다.
 */
export interface DialogueLine { speaker: string; text: string }
export interface ThemeScene {
  /** 그날 등장인물 대화(ai 테마: 초3·초4 3~4줄, 초5·초6 2~3줄, 끝 두 줄은 증거 발견 줄과 뭉치의 수사 연결 문장). 없으면 빈 배열 */
  dialogue: DialogueLine[]
  /** 관리자가 넣은 요일 영상(presigned URL). ai 테마 초안 채택 테마는 요일 영상이 없어 null(#437 2026-11-11) */
  videoUrl: string | null
}

/** 답을 하나라도 쓴 시도(보낸 답 또는 저장된 초안의 글·고른 것). 이런 시도는 이어서 풀 때 오늘 장면 없이 바로 답변 작성으로(#807) */
export function attemptStarted(a: Pick<import('./classroom.ts').Attempt, 'answers' | 'draft'>) {
  if (a.answers.length > 0) return true
  const v = a.draft?.answer
  if (!v) return false
  const filled = (s: string | undefined) => !!s && s.trim().length > 0
  return filled(v.text) || filled(v.finalAnswer) || v.steps.some(filled) ||
    filled(v.essay.claim) || v.essay.reasons.some(filled) || filled(v.essay.rebuttal) ||
    v.choiceIds.length > 0 || v.assignments.length > 0
}

const record = (v: unknown) => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null)
const filled = (v: unknown): v is string => typeof v === 'string' && v.trim().length > 0

/** 없거나 객체가 아니면 null. 화자·대사가 빈 줄은 빼고 읽는다(그 줄만 못 보여 줄 뿐 문제는 풀 수 있어야 함) */
export function readThemeScene(raw: unknown): ThemeScene | null {
  const v = record(raw)
  if (!v) return null
  const lines = Array.isArray(v.dialogue) ? v.dialogue : []
  return {
    dialogue: lines.flatMap((x) => {
      const line = record(x)
      return line && filled(line.speaker) && filled(line.text) ? [{ speaker: line.speaker.trim(), text: line.text.trim() }] : []
    }),
    videoUrl: filled(v.videoUrl) ? v.videoUrl : null,
  }
}
