import type {
  AnswerContent,
  AnalysisResult,
  Attempt,
  Child,
  DemoScenario,
  Draft,
  Feedback,
  Mission,
  Period,
  PublicAttempt,
  Reflection,
  Report,
  Session,
  StudentHome,
} from '../../domain/classroom.ts'
export interface ClassroomGateway {
  readonly demo: boolean
  setScenario: (s: DemoScenario) => void
  login: (email: string, password: string) => Promise<Session>
  logout: () => Promise<void>
  children: () => Promise<Child[]>
  enterStudent: (child: Child) => Promise<Session>
  missions: (child: Child) => Promise<Mission[]>
  home: (child: Child) => Promise<StudentHome>
  restore: () => Promise<Session>
  mission: (id: string, child: Child) => Promise<Mission>
  records: (child: Child, role: 'STUDENT' | 'PARENT', period: Period) => Promise<PublicAttempt[]>
  record: (child: Child, id: string) => Promise<PublicAttempt>
  start: (mission: Mission, child: Child) => Promise<Attempt>
  attempt: (id: string) => Promise<Attempt>
  saveDraft: (id: string, draft: Draft) => Promise<Draft>
  hint: (id: string) => Promise<string>
  submit: (id: string, answer: AnswerContent, key: string, followupId?: string) => Promise<Attempt>
  feedback: (
    id: string,
    answerId: string,
    onStatus: (s: Feedback) => void,
    signal?: AbortSignal,
  ) => Promise<Feedback>
  finish: (id: string) => Promise<Attempt>
  reflect: (id: string, reflection: Reflection) => Promise<Attempt>
  report: (child: Child, period: Period, revision?: number) => Promise<Report>
  regenerate: (report: Report) => Promise<Report>
  analyze: (child: Child, period: Period, question: string) => Promise<AnalysisResult>
}
