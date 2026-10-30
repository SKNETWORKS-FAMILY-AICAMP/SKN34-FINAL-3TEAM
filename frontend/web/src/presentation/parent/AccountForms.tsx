import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import type { Child } from '../../domain/classroom.ts'
import type { Consent, ConsentDocument } from '../../domain/parent.ts'
import { parentApi } from '../../data/parent/api.ts'
import { demoSignup } from '../../data/parent/demoSignup.ts'
import { useParentQuery, useParentMutation } from '../../data/parent/queries.ts'
import { isDemo } from '../../data/classroom/useClassroom.ts'
import { Workspace, QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
export function ConsentFields({
  documents,
  value,
  onChange,
}: {
  documents: ConsentDocument[]
  value: Consent[]
  onChange: (v: Consent[]) => void
}) {
  return (
    <div className="ws-stack">
      {documents.map((d) => (
        <div key={d.documentId}>
          <details>
            <summary>
              {d.title} · v{d.version} · {d.required ? '필수' : '선택'}
            </summary>
            <p>{d.content}</p>
          </details>
          <label className="ws-check">
            <input
              type="checkbox"
              checked={!!value.find((c) => c.documentId === d.documentId && c.version === d.version)?.agreed}
              required={d.required}
              onChange={(e) =>
                onChange([
                  ...value.filter((c) => c.documentId !== d.documentId),
                  { documentId: d.documentId, version: d.version, agreed: e.target.checked },
                ])
              }
            />
            {d.title}에 동의합니다.
          </label>
        </div>
      ))}
    </div>
  )
}
export function SignupPage() {
  if (!isDemo) return <Workspace title="이용 등록" nav={[]}><section className="ws-card">
    <h2>Google 계정으로 시작하기</h2><p>로그인 후 이용 동의와 자녀 등록을 진행합니다.</p>
    <a className="cj-primary" href="/api/v1/auth/google/authorize">Google 계정으로 계속하기</a>
  </section></Workspace>
  return <DemoSignupPage />
}
function DemoSignupPage() {
  const navigate = useNavigate(),
    documents = useParentQuery(['consents'], (signal) => parentApi.documents(signal)),
    signup = useParentMutation(demoSignup)
  const [email, setEmail] = useState(''),
    [password, setPassword] = useState(isDemo ? 'demo-only' : ''),
    [name, setName] = useState(''),
    [consents, setConsents] = useState<Consent[]>([]),
    [done, setDone] = useState(false)
  return (
    <Workspace title="이용 등록" nav={[]}>
      <section className="ws-card" style={{ maxWidth: 680, margin: 'auto' }}>
        <h1>생각을 기록하는 공책을 시작합니다.</h1>
        <p>학부모가 등록하고 자녀를 추가합니다. 학생 계정은 따로 만들지 않습니다.</p>
        {isDemo && (
          <p>
            개발 시연입니다. example.test 이메일만 사용해 주세요. 가입 뒤 시연 로그인 비밀번호는
            demo-only입니다.
          </p>
        )}
        {done ? (
          <>
            <p role="status">이용 등록이 완료되었습니다. 로그인 후 자녀를 등록해 주세요.</p>
            <button className="cj-primary" onClick={() => navigate('/login')}>
              로그인하기
            </button>
          </>
        ) : (
          <form
            className="ws-form"
            onSubmit={(e) => {
              e.preventDefault()
              void signup
                .mutateAsync({ email, password, name, consents })
                .then(() => {
                  setPassword('')
                  setDone(true)
                })
                .catch(() => {})
            }}
          >
            <label>
              이메일
              <input
                aria-label="가입 이메일"
                type="email"
                value={email}
                required
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="off"
              />
            </label>
            <label>
              비밀번호
              <input
                aria-label="가입 비밀번호"
                type="password"
                value={password}
                required
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
            </label>
            <label>
              이름
              <input
                aria-label="가입 이름"
                value={name}
                required
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <QueryFeedback query={documents} />
            {documents.data && !documents.error && (
              <ConsentFields
                documents={documents.data.items.filter((d) => d.kind !== 'GUARDIAN')}
                value={consents}
                onChange={setConsents}
              />
            )}
            <button
              className="cj-primary"
              disabled={!documents.data || !!documents.error || signup.isPending}
            >
              동의하고 등록하기
            </button>
            <ErrorNotice
              error={signup.error}
              retry={() => {
                void signup.mutateAsync({ email, password, name, consents }).catch(() => {})
              }}
            />
            <Link to="/login">로그인으로 돌아가기</Link>
          </form>
        )}
      </section>
    </Workspace>
  )
}
export function ChildRegistration({ onCreated }: { onCreated: (c: Child) => void }) {
  const documents = useParentQuery(['consents'], (signal) => parentApi.documents(signal)),
    register = useParentMutation(parentApi.register),
    [nickname, setNickname] = useState(''),
    [grade, setGrade] = useState(3),
    [birthYear, setBirthYear] = useState(2017),
    [maxYear] = useState(() => new Date().getFullYear()),
    [consents, setConsents] = useState<Consent[]>([])
  return (
    <section className="ws-card">
      <h2>자녀 등록</h2>
      <p>
        다른 보호자가 등록한 학생 연결은 지원하지 않습니다. 등록한 보호자 한 분에게만 소속되며 최대
        3명까지 등록할 수 있습니다.
      </p>
      <form
        className="ws-form"
        onSubmit={(e) => {
          e.preventDefault()
          void register
            .mutateAsync({ nickname, grade, birthYear, consents })
            .then(onCreated)
            .catch(() => {})
        }}
      >
        <label>
          자녀 별명
          <input
            aria-label="자녀 별명"
            value={nickname}
            required
            onChange={(e) => setNickname(e.target.value)}
          />
        </label>
        <label>
          자녀 학년
          <select
            aria-label="자녀 학년"
            value={grade}
            onChange={(e) => setGrade(Number(e.target.value))}
          >
            {[3, 4, 5, 6].map((g) => (
              <option key={g} value={g}>
                초등 {g}학년
              </option>
            ))}
          </select>
        </label>
        <label>
          출생연도
          <input
            aria-label="출생연도"
            type="number"
            min={1900}
            max={maxYear}
            value={birthYear}
            required
            onChange={(e) => setBirthYear(Number(e.target.value))}
          />
        </label>
        <QueryFeedback query={documents} />
        {documents.data && !documents.error && (
          <ConsentFields
            documents={documents.data.items.filter((d) => d.kind === 'GUARDIAN')}
            value={consents}
            onChange={setConsents}
          />
        )}
        <button
          className="cj-primary"
          disabled={register.isPending || !documents.data || !!documents.error}
        >
          자녀 등록하기
        </button>
        <ErrorNotice error={register.error} />
      </form>
    </section>
  )
}
export function ProfileSettings({ child }: { child: Child }) {
  const [name, setName] = useState(''),
    [nickname, setNickname] = useState(child.nickname),
    [grade, setGrade] = useState(child.grade),
    [notice, setNotice] = useState(''),
    updateMe = useParentMutation(parentApi.updateMe),
    update = useParentMutation((d: { nickname?: string; grade?: number }) =>
      parentApi.updateChild(child.id, d),
    ),
    me = useParentQuery(['me'], () => parentApi.me())
  return (
    <div className="ws-grid">
      <section className="ws-card">
        <h2>본인 정보</h2>
        <QueryFeedback query={me} />
        <p>현재 이름: {me.data?.name ?? '확인 중'}</p>
        <form
          className="ws-form"
          onSubmit={(e) => {
            e.preventDefault()
            void updateMe
              .mutateAsync(name)
              .then(() => setNotice('본인 정보를 저장했습니다.'))
              .catch(() => {})
          }}
        >
          <label>
            새 이름
            <input
              aria-label="새 이름"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <button className="cj-primary" disabled={updateMe.isPending}>
            이름 저장
          </button>
          <ErrorNotice error={updateMe.error} />
        </form>
      </section>
      <section className="ws-card">
        <h2>자녀 정보</h2>
        <p>학년 변경은 이후 제공 문제에만 적용됩니다. 과거 답변과 문항은 변경하지 않습니다.</p>
        <p>현재 로그인 권한으로 별명과 학년을 수정합니다. 연결 해제·삭제는 아래에서 별도로 본인 확인합니다.</p>

        <form
          className="ws-form"
          onSubmit={(e) => {
            e.preventDefault()
            // PATCH /children/{id}는 nickname·grade 모두 선택이다(api-spec 5.6). 바뀐 필드만 보낸다.
            const changes = {
              ...(nickname.trim() !== child.nickname ? { nickname: nickname.trim() } : {}),
              ...(grade !== child.grade ? { grade } : {}),
            }
            if (!Object.keys(changes).length) return setNotice('바뀐 내용이 없습니다.')
            void update
              .mutateAsync(changes)
              .then(() => setNotice('자녀 정보를 저장했습니다.'))
              .catch(() => {})
          }}
        >
          <label>
            새 자녀 별명
            <input
              aria-label="새 자녀 별명"
              required
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
            />
          </label>
          <label>
            새 학년
            <select
              aria-label="새 학년"
              value={grade}
              onChange={(e) => setGrade(Number(e.target.value))}
            >
              {[3, 4, 5, 6].map((g) => (
                <option key={g} value={g}>
                  초등 {g}학년
                </option>
              ))}
            </select>
          </label>
          <button className="cj-primary" disabled={update.isPending}>
            자녀 정보 저장
          </button>
          <ErrorNotice error={update.error} />
        </form>
      </section>
      <p role="status">{notice}</p>
    </div>
  )
}
