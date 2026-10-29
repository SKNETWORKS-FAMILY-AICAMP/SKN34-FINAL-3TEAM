import { useState } from 'react'
import { ArrowUpRight, MessagesSquare, RefreshCw } from 'lucide-react'
import {
  isDemo,
  displayPeriods,
  useParentActions,
  useReport,
} from '../../data/classroom/useClassroom.ts'
import { shortRange, thinkingLabels } from '../../domain/classroom.ts'
import type { Child, Period } from '../../domain/classroom.ts'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { QueryStateNotice } from '../common/QueryStateNotice.tsx'

const { previousWeek, thisWeek, olderWeek } = displayPeriods
export function ParentReport({
  child,
  onEvidence,
  onAnalysis,
}: {
  child: Child
  onEvidence: (id: string) => void
  onAnalysis: (p: Period) => void
}) {
  const [period, setPeriod] = useState<Period>(previousWeek),
    [revision, setRevision] = useState<number | undefined>(),
    [download, setDownload] = useState(false)
  const query = useReport(child, period, revision),
    actions = useParentActions(),
    r = query.data
  return (
    <>
      <div className="cj-feedbar">
        <h1>주간 리포트</h1>
        <div className="cj-filters">
          <select
            aria-label="리포트 주간"
            value={period.from}
            onChange={(e) => {
              setPeriod(
                e.target.value === thisWeek.from
                  ? thisWeek
                  : e.target.value === previousWeek.from
                    ? previousWeek
                    : olderWeek,
              )
              setRevision(undefined)
            }}
          >
            <option value={previousWeek.from}>지난주 · {shortRange(previousWeek)}</option>
            <option value={thisWeek.from}>이번 주 · {shortRange(thisWeek)}</option>
            <option value={olderWeek.from}>{shortRange(olderWeek)}</option>
          </select>
          {r && (
            <select
              aria-label="리포트 판"
              value={revision ?? 'latest'}
              onChange={(e) =>
                setRevision(e.target.value === 'latest' ? undefined : Number(e.target.value))
              }
            >
              <option value="latest">최신판</option>
              {r.revisions.map((v) => (
                <option value={v} key={v}>
                  {v}판
                </option>
              ))}
            </select>
          )}
        </div>
      </div>
      <div className="cj-feed">
        <p className="ux-context">
          {child.nickname} · {period.from}~{period.to} (KST 월~일)
          <br />
          <small>
            주간 종료 다음 월요일 오전 7시 생성. 공책·분석의 최근 7일과 조회 기간이 다를 수
            있습니다.
          </small>
        </p>
        {query.isPending && (
          <div role="status" className="cj-empty">
            리포트를 읽는 중입니다.
          </div>
        )}
        <ErrorNotice
          error={query.error}
          retry={() => {
            void query.refetch()
          }}
        />
        {r && (
          <article className="cj-sheet">
            <small>
              {r.revision}판 · {r.status}
            </small>
            <h2>
              {r.status === 'QUEUED' || r.status === 'RUNNING'
                ? '리포트 생성 중입니다.'
                : r.status === 'FAILED'
                  ? '리포트 생성에 실패했습니다.'
                  : r.state === 'NO_RECORD'
                    ? '이 주에는 학습 기록이 없습니다.'
                    : `${child.nickname}의 한 주`}
            </h2>
            {['QUEUED', 'RUNNING'].includes(r.status) && (
              <p>
                처리 중인 결과를 완료로 표시하지 않습니다. 이번 주 리포트는 다음 월요일 오전 7시
                생성 대상입니다.
              </p>
            )}
            {r.status === 'FAILED' && (
              <p>
                생성 실패는 기록 없음과 다릅니다. 완료된 이전 판이 있다면 판 선택에서 확인해 주세요.
              </p>
            )}
            {r.status === 'COMPLETED' && (
              <>
                {r.state === 'INSUFFICIENT_SAMPLE' && (
                  <QueryStateNotice state="INSUFFICIENT_SAMPLE">
                    기록이 5건보다 적어 비율 대신 개수로 표시합니다. 능력이 부족하다는 뜻은
                    아닙니다.
                  </QueryStateNotice>
                )}
                {r.metrics.map((m) => (
                  <details className="ux-metric" key={m.label}>
                    <summary>
                      {m.label}
                      <strong>{m.count}개</strong>
                    </summary>
                    <p>
                      기간: {m.period.from}~{m.period.to}
                      <br />
                      분자 {m.numerator} / 분모 {m.denominator}
                      <br />
                      계산식: {m.formula}
                      <br />
                      출처: {m.sourceType}
                    </p>
                  </details>
                ))}
                {child.plan !== 'FREE' ? (
                  <>
                    {r.narrative && <p className="cj-quote">{r.narrative}</p>}
                    <h3>질문 전후의 원문</h3>
                    {r.records
                      .filter((a) => a.answers.length > 1)
                      .map((a) => (
                        <section className="ux-report-record" key={a.attemptId}>
                          <small>{a.mission.title}</small>
                          <div className="ux-compare">
                            <div>
                              <small>처음</small>
                              <p>{a.answers[0].text}</p>
                            </div>
                            <div>
                              <small>마지막</small>
                              <p>{a.answers.at(-1)!.text}</p>
                            </div>
                          </div>
                          <button
                            type="button"
                            className="cj-back"
                            onClick={() => onEvidence(a.attemptId)}
                          >
                            원문·질문·돌아보기 <ArrowUpRight />
                          </button>
                        </section>
                      ))}
                    <h3>다섯 가지 생각 활동</h3>
                    {Object.entries(thinkingLabels).map(([type, label]) => (
                      <div className="cj-metric-line" key={type}>
                        <span>{label}</span>
                        <span>
                          {r.records.some((a) => a.mission.thinkingType === type)
                            ? `${r.records.filter((a) => a.mission.thinkingType === type).length}개 활동`
                            : '확인된 기록 없음'}
                        </span>
                      </div>
                    ))}
                    <h3 style={{ marginTop: 22 }}>이번 주 저녁 질문</h3>
                    <p>
                      {r.eveningQuestion ??
                        (isDemo && r.records.length
                          ? '시연 질문: 질문을 받고 어떤 생각을 더 남기게 되었나요?'
                          : '서버에서 확인된 저녁 질문이 아직 없습니다.')}
                    </p>
                    <button
                      type="button"
                      className="cj-secondary"
                      onClick={() => onAnalysis(period)}
                    >
                      <MessagesSquare />이 자녀·이 기간으로 물어보기
                    </button>
                  </>
                ) : (
                  <div className="ux-help">
                    무료 이용에서는 리포트 수치만 제공됩니다. 원문 기록은 공책에서, 분석 대화와 전체
                    리포트는 프리미엄에서 확인합니다.
                  </div>
                )}
              </>
            )}
            <div className="cj-modal-actions">
              <button
                type="button"
                className="cj-secondary"
                onClick={() => {
                  void query.refetch()
                }}
              >
                <RefreshCw />
                상태 확인
              </button>
              {r.status === 'COMPLETED' && (
                <>
                  <button
                    type="button"
                    className="cj-secondary"
                    disabled={r.regenerations >= 1 || actions.regenerate.isPending}
                    onClick={() => {
                      void actions.regenerate
                        .mutateAsync(r)
                        .then(() => setRevision(undefined))
                        .catch(() => {})
                    }}
                  >
                    {r.regenerations ? '재생성 1회 사용' : '새 판으로 다시 만들기 (1회)'}
                  </button>
                  <button type="button" className="cj-secondary" onClick={() => setDownload(true)}>
                    PDF·Markdown 다운로드
                  </button>
                </>
              )}
            </div>
            <ErrorNotice error={actions.regenerate.error} />
          </article>
        )}
      </div>
      {download && (
        <Modal title="리포트 파일 다운로드" onClose={() => setDownload(false)}>
          <p>
            실제 연결 시 권한 확인 후 `/reports/{'{reportId}'}/download?format=pdf|md`에서 받은 만료
            시간이 있는 URL로 다운로드합니다.
          </p>
          <p className="ux-help">
            현재 develop에는 다운로드 Controller·파일 생성 기능이 아직 없습니다. 임의 파일이나 성공
            링크를 만들지 않았습니다.
          </p>
        </Modal>
      )}
    </>
  )
}

export function ParentAnalysis({
  child,
  period,
  onEvidence,
}: {
  child: Child
  period: Period
  onEvidence: (id: string) => void
}) {
  const actions = useParentActions(),
    [question, setQuestion] = useState('질문을 받고 무엇을 더 썼나요?')
  const result = actions.analyze.data
  return (
    <>
      <div className="cj-feedbar">
        <h1>기록에 물어보기</h1>
      </div>
      <div className="cj-feed">
        <article className="cj-sheet">
          <small>
            {child.nickname} · {period.from}~{period.to}
          </small>
          <h2>아이의 기록에서 확인합니다.</h2>
          {child.plan === 'FREE' ? (
            <div className="ux-help">
              분석 대화는 프리미엄에서 이용할 수 있습니다. 무료 이용에서는 질문 요청을 보내지
              않습니다.
            </div>
          ) : (
            <>
              <div className="ux-question-buttons">
                {['질문을 받고 무엇을 더 썼나요?', '처음 남긴 답을 보여 주세요.'].map((q) => (
                  <button
                    type="button"
                    className="cj-secondary"
                    key={q}
                    onClick={() => setQuestion(q)}
                  >
                    {q}
                  </button>
                ))}
              </div>
              <label className="cj-field">
                질문
                <textarea
                  aria-label="기록에 물어볼 질문"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  maxLength={1000}
                />
              </label>
              <div className="cj-modal-actions">
                <button
                  type="button"
                  className="cj-primary"
                  disabled={!question.trim() || actions.analyze.isPending}
                  onClick={() => {
                    void actions.analyze.mutateAsync({ child, period, question }).catch(() => {})
                  }}
                >
                  기록 확인하기
                </button>
              </div>
              {actions.analyze.isPending && (
                <p role="status">
                  기록 조회·계산·숫자와 인용 대조 중입니다. 검증 전 임시 문장은 확정 답변으로
                  표시하지 않습니다.
                </p>
              )}
              <ErrorNotice error={actions.analyze.error} />
              {result && !actions.analyze.isPending && !actions.analyze.error && (
                <section aria-live="polite" className="ux-analysis-result">
                  <small>
                    {result.source === 'TEMPLATE'
                      ? `규칙 응답 모드 · ${result.fallback?.reason ?? '대조 실패 또는 LLM 장애'}`
                      : '숫자·인용 대조 완료'}
                  </small>
                  <p>{result.answer}</p>
                  {result.evidence.map((e) => (
                    <div className="cj-quote" key={e.answerId}>
                      {e.available ? (
                        <>
                          {e.quote}
                          <br />
                          <button
                            type="button"
                            className="cj-back"
                            onClick={() => onEvidence(e.attemptId)}
                          >
                            원문 확인 <ArrowUpRight />
                          </button>
                        </>
                      ) : (
                        '삭제된 근거 · 이용 불가 (다른 기록으로 대체하지 않습니다.)'
                      )}
                    </div>
                  ))}
                </section>
              )}
            </>
          )}
        </article>
      </div>
    </>
  )
}
