import { ApiError } from '../apiClient.ts'
import {
  answerText,
  blankAnswer,
  canAddAnswer,
  canFinish,
  counts,
  eligibleRecords,
  inPeriod,
  previousWeek,
  publicAttempt,
  validateAnswer,
} from '../../domain/classroom.ts'
import type {
  Answer,
  Attempt,
  Child,
  DemoScenario,
  Feedback,
  Mission,
  Period,
  Reflection,
  Report,
  Session,
} from '../../domain/classroom.ts'
import type { ClassroomGateway } from './gateway.ts'
import { DraftConflictError } from './errors.ts'
export { DraftConflictError } from './errors.ts'

const copy = <T>(value: T): T => structuredClone(value)
const fail = (code: string, detail: string, status = 409): never => {
  throw new ApiError({ code, title: detail, detail, status })
}
const pause = () => new Promise<void>((resolve) => setTimeout(resolve, 80))
export function demoMissions(grade: number): Mission[] {
  return [
    {
      id: `${grade}-solve`,
      title: '같은 수를 다르게 세기',
      subject: '수학',
      grade,
      thinkingType: 'SOLVE',
      inputType: 'SOLUTION_STEPS',
      question: '한 상자에 사과가 3개씩, 상자가 2개 있어요. 사과의 수와 어떻게 셌는지 남겨 주세요.',
      hint: '상자 하나에 든 수와 상자의 수를 나누어 살펴보세요.',
      scene: 'math',
    },
    {
      id: `${grade}-analyze`,
      title: '같은 날 심었는데',
      subject: '과학',
      grade,
      thinkingType: 'ANALYZE',
      inputType: 'CHOICE',
      question: '두 화분에서 눈으로 확인할 수 있는 차이는 무엇인가요?',
      hint: '잎의 크기와 색을 비교해 보세요.',
      scene: 'science',
      choices: [
        { id: 'leaf', label: '잎의 색과 크기' },
        { id: 'date', label: '심은 날짜' },
        { id: 'soil', label: '흙의 무게' },
      ],
    },
    {
      id: `${grade}-evaluate`,
      title: '도서관에 만화책을 더 둘까요?',
      subject: '국어',
      grade,
      thinkingType: 'EVALUATE',
      inputType: grade >= 5 ? 'ESSAY' : 'NARRATIVE',
      question: '도서관에 만화책을 더 두면 좋을까요? 내 의견과 그렇게 생각한 까닭을 남겨 주세요.',
      hint: '직접 읽었던 책과, 다른 의견을 가진 친구를 떠올려 보세요.',
      scene: 'korean',
    },
    {
      id: `${grade}-create`,
      title: '상자의 새로운 쓰임',
      subject: '국어',
      grade,
      thinkingType: 'CREATE',
      inputType: 'NARRATIVE',
      question: '빈 상자를 새롭게 쓴다면 무엇을 만들고 싶나요? 어떻게 쓸지도 적어 주세요.',
      hint: '모양을 바꾸거나 다른 물건과 함께 써 볼까요?',
      scene: 'math',
    },
    {
      id: `${grade}-reflect`,
      title: '다시 해 본 경험',
      subject: '국어',
      grade,
      thinkingType: 'REFLECT',
      inputType: 'NARRATIVE',
      question: '처음에는 어려웠지만 다시 해 본 일을 떠올려 보세요. 무엇을 바꾸었나요?',
      hint: '처음 방법과 다음에 바꾼 방법을 나누어 적어 보세요.',
      scene: 'korean',
    },
  ]
}
export interface DemoSnapshot {
  children?: Child[]
  catalog?: Mission[]
  attempts: Attempt[]
  session: Session | null
  serial: number
  keys: [string, string][]
  reports: [string, Report[]][]
}
export function createDemoGateway(): ClassroomGateway & {
  snapshot: () => DemoSnapshot
  restoreSnapshot: (snapshot: DemoSnapshot) => void
  replaceChildren: (children: Child[]) => void
  publishCatalog: (id: string, mission: Mission | null) => void
} {
  const children: Child[] = [
    { id: 'demo-seoyun', nickname: '서윤', grade: 3, birthYear: 2017, plan: 'PREMIUM' },
    { id: 'demo-doyun', nickname: '도윤', grade: 5, birthYear: 2015, plan: 'FREE' },
  ]
  const db = new Map<string, Attempt>(),
    keys = new Map<string, string>(),
    reportVersions = new Map<string, Report[]>()
  const catalog = new Map<string, Mission>()
  let session: Session | null = null,
    scenario: DemoScenario = 'normal',
    serial = 0
  const faults = new Set<string>()
  function requireParent(child?: Child) {
    if (session?.role !== 'PARENT') fail('FORBIDDEN', '학부모 로그인이 필요합니다.', 403)
    if (child && !children.some((c) => c.id === child.id))
      fail('CHILD_NOT_LINKED', '연결된 자녀가 아닙니다.', 403)
  }
  function requireStudent(childId?: string) {
    if (session?.role !== 'STUDENT' || (childId && session.child?.id !== childId))
      fail('FORBIDDEN', '현재 학생의 기록만 사용할 수 있어요.', 403)
  }
  function own(id: string): Attempt {
    const a = db.get(id)
    if (!a) fail('NOT_FOUND', '활동을 찾을 수 없어요.', 404)
    requireStudent(a!.studentId)
    return a!
  }
  function once(key: string) {
    if (faults.has(key)) return false
    faults.add(key)
    return true
  }
  function availableMissions(child: Child): Mission[] {
    const all = [...demoMissions(child.grade), ...catalog.values()]
      .filter(
        (m) =>
          m.grade === child.grade ||
          (!!m.gradeMax && m.grade <= child.grade && child.grade <= m.gradeMax),
      )
      .map((m) => ({ ...m, grade: child.grade }))
    if (scenario === 'input-fixtures')
      all.push(
        {
          id: `${child.grade}-ordering`,
          title: '씨앗의 자라는 순서',
          subject: '과학',
          grade: child.grade,
          thinkingType: 'ANALYZE',
          inputType: 'ORDERING',
          question: '씨앗이 자라는 순서대로 골라 주세요.',
          hint: '먼저 일어나는 변화를 떠올려 보세요.',
          scene: 'science',
          choices: [
            { id: 'sprout', label: '싹이 나요' },
            { id: 'seed', label: '씨앗을 심어요' },
            { id: 'leaf', label: '잎이 자라요' },
          ],
        },
        {
          id: `${child.grade}-classification`,
          title: '이 물건은 어디에 넣을까요?',
          subject: '과학',
          grade: child.grade,
          thinkingType: 'ANALYZE',
          inputType: 'CLASSIFICATION',
          question: '각 물건을 알맞은 그룹에 넣어 주세요.',
          hint: '자석에 붙을지 생각해 보세요.',
          scene: 'science',
          choices: [
            { id: 'nail', label: '철 못' },
            { id: 'paper', label: '종이' },
            { id: 'clip', label: '철 클립' },
          ],
          categories: [
            { id: 'magnetic', label: '자석에 붙어요' },
            { id: 'other', label: '자석에 붙지 않아요' },
          ],
        },
      )
    return all.map((m, i) => {
      const rows = [...db.values()].filter((a) => a.studentId === child.id && a.mission.id === m.id)
      const active = rows.find((a) => a.status === 'IN_PROGRESS')
      const latest = active ?? rows.at(-1)
      return {
        ...m,
        status: latest?.status ?? 'NOT_STARTED',
        attemptId: latest?.attemptId,
        position: i + 1,
        total: all.length,
      }
    })
  }
  function nextFeedback(a: Attempt): Feedback {
    const last = a.answers.at(-1)!,
      correct = last.inputType === 'CHOICE' && last.text.includes('잎의 색과 크기')
    const result =
      scenario === 'correct'
        ? 'CORRECT'
        : scenario === 'partial'
          ? 'PARTIAL'
          : scenario === 'rethink'
            ? 'RETHINK'
            : correct
              ? 'CORRECT'
              : 'HELD'
    const noMore = (result === 'CORRECT' && last.inputType === 'CHOICE') || a.answers.length >= 3
    const quote = last.text.slice(0, Math.min(50, last.text.length))
    return {
      status: 'DONE',
      judgment: {
        result,
        trial: !correct,
        heldReason: result === 'HELD' ? 'UNVERIFIED_SCOPE' : undefined,
        elements:
          result === 'HELD'
            ? []
            : [
                {
                  elementId: 'thought',
                  label: '내 생각을 표현했어요',
                  satisfied: result !== 'RETHINK',
                  quote: result !== 'RETHINK' ? quote : null,
                  sourceType: 'AI_OBSERVATION',
                },
                {
                  elementId: 'reason',
                  label: '까닭을 연결했어요',
                  satisfied: false,
                  quote: null,
                  sourceType: 'AI_OBSERVATION',
                },
              ],
      },
      nextActions: noMore ? ['FINISH'] : ['ANSWER_FOLLOWUP', 'FINISH'],
      followup: noMore
        ? undefined
        : {
            followupId: `${last.answerId}-question`,
            type:
              result === 'RETHINK'
                ? 'LOOK_AGAIN'
                : a.answers.length === 1
                  ? 'TELL_MORE'
                  : 'ONE_STEP_MORE',
            question:
              a.answers.length === 1
                ? '그렇게 생각한 까닭을 한 가지 더 남겨 주세요.'
                : '다른 방법이나 다른 의견으로도 생각해 볼 수 있을까요?',
            source: 'BANK',
          },
    }
  }
  function seed(child: Child, suffix: string, index: number, texts: string[], day: string) {
    const mission = demoMissions(child.grade)[index],
      id = `${child.id}-${suffix}`
    const a: Attempt = {
      attemptId: id,
      studentId: child.id,
      mission,
      status: 'COMPLETED',
      finishedAt: `${day}T16:00:00+09:00`,
      answers: [],
      reflection: { difficulty: '보통', text: '처음 쓴 생각에 경험을 보탰어요.' },
      helped: false,
    }
    for (const [i, text] of texts.entries()) {
      a.answers.push({
        answerId: `${id}-a${i + 1}`,
        version: i + 1,
        submittedAt: `${day}T15:0${i}:00+09:00`,
        inputType: mission.inputType,
        text,
        feedback: { status: 'PENDING', nextActions: [] },
      })
      a.answers.at(-1)!.feedback = nextFeedback(a)
    }
    db.set(id, a)
  }
  seed(
    children[0],
    'math',
    0,
    [
      '답: 6개\n1. 한 상자에 3개씩 있어요.\n2. 3+3=6으로 더했어요.',
      '3은 한 상자에 든 수, 2는 상자의 수예요. 3×2로도 셀 수 있어요.',
    ],
    '2026-10-25',
  )
  seed(
    children[0],
    'writing',
    2,
    [
      '만화책을 더 두면 좋겠어요.',
      '과학 만화에서 자석이 철을 끌어당기는 그림을 보고 이해한 적이 있기 때문이에요.',
    ],
    '2026-10-24',
  )
  seed(
    children[0],
    'reflection',
    4,
    ['줄넘기가 어려웠어요. 천천히 한 번씩 넘는 것으로 바꾸니 할 수 있었어요.'],
    '2026-10-23',
  )
  seed(
    children[1],
    'writing',
    2,
    [
      '만화책을 더 두면 좋겠어요.\n그림으로 어려운 내용을 이해할 수 있어요.\n책에 흥미가 없는 친구도 읽기 시작할 수 있어요.\n글책도 함께 갖추어 골고루 읽으면 좋겠어요.',
    ],
    '2026-10-25',
  )
  function records(child: Child, period: Period) {
    return [...db.values()]
      .filter(
        (a) => a.studentId === child.id && a.answers.some((v) => inPeriod(v.submittedAt, period)),
      )
      .map(publicAttempt)
      .reverse()
  }
  function makeReport(child: Child, period: Period, revision = 1): Report {
    const rows = eligibleRecords(records(child, period), period),
      metrics = counts(rows, period)
    return {
      reportId: `${child.id}-${period.from}`,
      childId: child.id,
      period: copy(period),
      revision,
      revisions: [1],
      status: 'COMPLETED',
      state: metrics[0].state,
      metrics,
      records: rows,
      narrative:
        child.plan === 'PREMIUM'
          ? '이 화면의 기록에서 계산한 개수와 아이의 원문을 함께 읽어 보세요. 사고력 수준을 진단하는 결과가 아닙니다.'
          : null,
      regenerations: 0,
    }
  }
  return {
    snapshot() {
      return copy({
        children,
        catalog: [...catalog.values()],
        attempts: [...db.values()],
        session,
        serial,
        keys: [...keys.entries()],
        reports: [...reportVersions.entries()],
      })
    },
    restoreSnapshot(data) {
      if (data.children) children.splice(0, children.length, ...copy(data.children))
      if (data.catalog) {
        catalog.clear()
        for (const m of data.catalog) catalog.set(m.id, copy(m))
      }
      db.clear()
      for (const a of data.attempts) db.set(a.attemptId, copy(a))
      session = copy(data.session)
      serial = data.serial
      keys.clear()
      for (const [k, v] of data.keys) keys.set(k, v)
      reportVersions.clear()
      for (const [k, v] of data.reports) reportVersions.set(k, copy(v))
    },
    replaceChildren(items) {
      children.splice(0, children.length, ...copy(items))
    },
    publishCatalog(id, m) {
      if (m) catalog.set(id, copy(m))
      else catalog.delete(id)
    },
    demo: true,
    setScenario(s) {
      scenario = s
      faults.clear()
    },
    async login(email, password) {
      await pause()
      if (!email.includes('@') || !password)
        fail('UNAUTHENTICATED', '이메일과 비밀번호를 확인해 주세요.', 401)
      session = { role: 'PARENT' }
      return copy(session)
    },
    async logout() {
      session = null
    },
    async restore() {
      if (!session) fail('UNAUTHENTICATED', '로그인이 필요합니다.', 401)
      return copy(session!)
    },
    async home(child) {
      requireStudent(child.id)
      if (scenario === 'home-fail') fail('QUERY_FAILED', '학생 홈을 불러오지 못했습니다.', 503)
      const missions = availableMissions(child),
        resume =
          [...db.values()]
            .filter((a) => a.studentId === child.id && a.status === 'IN_PROGRESS')
            .at(-1) ?? null
      return copy({
        student: child,
        period: { from: '2026-10-20', to: '2026-10-26' },
        state:
          scenario === 'home-processing'
            ? 'PROCESSING'
            : scenario === 'home-empty'
              ? 'NO_RECORD'
              : scenario === 'home-small'
                ? 'INSUFFICIENT_SAMPLE'
                : 'OK',
        resume: scenario === 'home-empty' ? null : resume,
        missions,
      })
    },
    async children() {
      requireParent()
      return copy(children)
    },
    async enterStudent(child) {
      requireParent(child)
      session = { role: 'STUDENT', child: copy(child) }
      return copy(session)
    },
    async missions(child) {
      requireStudent(child.id)
      return copy(availableMissions(child))
    },
    async mission(id, child) {
      requireStudent(child.id)
      const mission = availableMissions(child).find((m) => m.id === id)
      if (!mission) fail('NOT_FOUND', '미션을 찾을 수 없습니다.', 404)
      return copy(mission!)
    },
    async records(child, role, period) {
      if (role === 'PARENT') requireParent(child)
      else requireStudent(child.id)
      return records(child, period)
    },
    async record(child, id) {
      requireParent(child)
      const a = db.get(id)
      if (!a || a.studentId !== child.id)
        fail('NOT_FOUND', '이 자녀의 원문을 찾을 수 없습니다.', 404)
      return publicAttempt(a!)
    },
    async start(mission, child) {
      requireStudent(child.id)
      if (mission.grade !== child.grade)
        fail('MISSION_NOT_AVAILABLE', '현재 학년에 제공되는 미션이 아닙니다.')
      const existing = [...db.values()].find(
        (a) =>
          a.studentId === child.id && a.mission.id === mission.id && a.status === 'IN_PROGRESS',
      )
      if (existing) return copy(existing)
      if (
        child.plan === 'FREE' &&
        [...db.values()].filter((a) => a.studentId === child.id && a.attemptId.startsWith('new-'))
          .length >= 3
      )
        fail('USAGE_LIMIT_REACHED', '무료 이용은 하루 미션 3개까지예요.', 429)
      const id = `new-${++serial}`
      const a: Attempt = {
        attemptId: id,
        studentId: child.id,
        mission: copy(mission),
        status: 'IN_PROGRESS',
        answers: [],
        helped: false,
        draft: { answer: blankAnswer(mission.inputType), memo: '', version: '0' },
      }
      db.set(id, a)
      return copy(a)
    },
    async attempt(id) {
      return copy(own(id))
    },
    async saveDraft(id, draft) {
      const a = own(id)
      if (a.finishedAt || a.status === 'COMPLETED')
        fail('ATTEMPT_CLOSED', '마무리한 활동은 더 작성할 수 없어요.')
      await pause()
      if (scenario === 'draft-fail' && once('draft-fail-' + id))
        fail('DRAFT_SAVE_FAILED', '초안 저장에 실패했어요. 작성한 내용은 화면에 남아 있어요.', 503)
      if (scenario === 'draft-conflict' && once('conflict-' + id)) {
        a.draft = {
          ...copy(draft),
          version: String(Number(draft.version) + 1),
          answer: { ...copy(draft.answer), text: '다른 화면에서 저장한 초안 예시입니다.' },
        }
        throw new DraftConflictError(copy(a.draft))
      }
      if (a.draft && draft.version !== a.draft.version) throw new DraftConflictError(copy(a.draft))
      a.draft = {
        ...copy(draft),
        version: String(Number(draft.version) + 1),
        savedAt: '2026-10-26T16:00:00+09:00',
      }
      return copy(a.draft)
    },
    async hint(id) {
      const a = own(id)
      a.helped = true
      return a.mission.hint
    },
    async submit(id, answer, key, followupId) {
      const a = own(id)
      const used = keys.get(id + ':' + key)
      if (used) return copy(db.get(used)!)
      if (!canAddAnswer(a)) fail('ATTEMPT_CLOSED', '현재는 답변을 더 제출할 수 없어요.')
      const message = validateAnswer(answer, a.mission)
      if (message) fail('ANSWER_INCOMPLETE', message, 422)
      if (a.answers.length && followupId !== a.answers.at(-1)?.feedback.followup?.followupId)
        fail('ANSWER_INCOMPLETE', '현재 추가 질문에 연결해 주세요.', 422)
      if (scenario === 'submit-fail' && once('submit-' + id))
        fail('ANSWER_SAVE_FAILED', '답변 저장에 실패했어요. 같은 답을 다시 보낼 수 있어요.', 503)
      const text = ['CHOICE', 'ORDERING'].includes(answer.inputType)
        ? answer.choiceIds
            .map((cid) => a.mission.choices?.find((c) => c.id === cid)?.label ?? cid)
            .join(' → ')
        : answerText(answer)
      const v: Answer = {
        answerId: `${id}-a${a.answers.length + 1}`,
        version: a.answers.length + 1,
        submittedAt: '2026-10-26T16:00:00+09:00',
        inputType: answer.inputType,
        text,
        followupId,
        feedback: { status: 'PENDING', nextActions: [] },
        content: copy(answer),
      }
      a.answers.push(v)
      if (a.draft)
        a.draft = {
          ...a.draft,
          answer: blankAnswer(a.mission.inputType),
          version: String(Number(a.draft.version) + 1),
        }
      keys.set(id + ':' + key, id)
      return copy(a)
    },
    async feedback(id, answerId, onStatus) {
      const a = own(id),
        answer = a.answers.find((v) => v.answerId === answerId)
      if (!answer) fail('NOT_FOUND', '답변을 찾을 수 없어요.', 404)
      if (answer!.feedback.status === 'DONE') return copy(answer!.feedback)
      answer!.feedback = { status: 'RUNNING', nextActions: [] }
      onStatus(copy(answer!.feedback))
      if (scenario === 'running' && once('running-' + answerId)) return copy(answer!.feedback)
      await pause()
      if (scenario === 'ai-fail' && once('ai-' + answerId)) {
        answer!.feedback = { status: 'FAILED', nextActions: [] }
        fail('AI_UNAVAILABLE', '답변은 저장했지만 피드백 처리가 실패했어요.', 503)
      }
      answer!.feedback = nextFeedback(a)
      if (scenario === 'held')
        answer!.feedback.judgment = {
          result: 'HELD',
          trial: true,
          heldReason: 'INSUFFICIENT_EVIDENCE',
        }
      return copy(answer!.feedback)
    },
    async finish(id) {
      const a = own(id)
      if (scenario === 'finish-unmet')
        fail(
          'REVEAL_CONDITION_UNMET',
          '마무리 조건을 아직 확인하지 못했습니다. 답변과 질문은 그대로 남아 있어요.',
        )
      if (!canFinish(a))
        fail('REVEAL_CONDITION_UNMET', '피드백 처리가 완료된 뒤 마무리할 수 있어요.')
      a.finishedAt = '2026-10-26T16:02:00+09:00'
      a.reveal = a.mission.id.endsWith('-solve')
        ? '한 상자에 3개씩 두 상자이므로 3+3=6 또는 3×2=6으로 셀 수 있어요.'
        : '예시와 똑같이 쓰지 않아도 됩니다. 내 생각과 까닭을 연결했는지 비교해 보세요.'
      a.revealKind = ['CHOICE', 'ORDERING', 'CLASSIFICATION', 'SOLUTION_STEPS'].includes(
        a.mission.inputType,
      )
        ? 'ANSWER'
        : 'EXAMPLE'
      if (a.mission.inputType === 'CHOICE')
        a.reveal = '눈으로 비교할 수 있는 것은 잎의 색과 크기예요.'
      if (a.mission.inputType === 'ORDERING') a.reveal = '씨앗을 심어요 → 싹이 나요 → 잎이 자라요.'
      if (a.mission.inputType === 'CLASSIFICATION')
        a.reveal = '철 못과 철 클립은 자석에 붙는 그룹, 종이는 붙지 않는 그룹이에요.'
      a.checklist = (a.answers.at(-1)?.feedback.judgment?.elements ?? []).map((e) => ({
        ...e,
        satisfied: !!e.satisfied && !!e.quote && a.answers.some((v) => v.text.includes(e.quote!)),
      }))
      return copy(a)
    },
    async reflect(id, reflection: Reflection) {
      const a = own(id)
      if (!a.finishedAt || !['쉬웠어', '보통', '어려웠어'].includes(reflection.difficulty))
        fail('REVEAL_CONDITION_UNMET', '마무리 후 난이도를 선택해 주세요.')
      if (a.status === 'COMPLETED') fail('ATTEMPT_CLOSED', '이미 돌아보기를 남긴 활동이에요.')
      a.reflection = copy(reflection)
      a.status = 'COMPLETED'
      return copy(a)
    },
    async report(child, period, revision) {
      requireParent(child)
      const key = child.id + period.from
      let list = reportVersions.get(key)
      if (!list) {
        const r = makeReport(child, period)
        list = [r]
        reportVersions.set(key, list)
      }
      const r = copy(list.find((v) => v.revision === revision) ?? list.at(-1)!)
      r.revisions = list.map((v) => v.revision)
      r.regenerations = list.length - 1
      if (scenario === 'report-fail') {
        r.status = 'FAILED'
        r.metrics = []
        r.records = []
      }
      if (period.from > previousWeek.to) {
        r.status = 'QUEUED'
        r.metrics = []
        r.records = []
      }
      return r
    },
    async regenerate(report) {
      requireParent()
      const child = children.find((c) => c.id === report.childId)!
      requireParent(child)
      const key = child.id + report.period.from,
        list = reportVersions.get(key) ?? [report]
      if (list.length > 1)
        fail('REGENERATE_NOT_ALLOWED', '같은 리포트는 한 번만 다시 만들 수 있어요.')
      const next = makeReport(child, report.period, 2)
      list.push(next)
      reportVersions.set(key, list)
      return copy({ ...next, revisions: [1, 2], regenerations: 1 })
    },
    async analyze(child, period, question) {
      requireParent(child)
      if (child.plan === 'FREE')
        fail('USAGE_LIMIT_REACHED', '분석 대화는 프리미엄에서 제공됩니다.', 429)
      const rows = eligibleRecords(records(child, period), period)
      const evidence = rows.map((r) => {
        const a = question.includes('처음') ? r.answers[0] : r.answers.at(-1)!
        return { attemptId: r.attemptId, answerId: a.answerId, quote: a.text, available: true }
      })
      return {
        source: 'TEMPLATE',
        answer: rows.length
          ? `선택한 기간에 답을 남긴 활동은 ${rows.length}개입니다. 아래는 실제 예시 기록의 원문입니다.`
          : '이 기간에는 제출 답변이 없습니다. 기록이 없는 상태를 능력 부족으로 해석하지 않습니다.',
        evidence,
        verification: { numbersMatched: true, quotesMatched: true },
        fallback: { reason: '화면 시연: LLM 미호출 · 규칙 응답 모드' },
      }
    },
  }
}
