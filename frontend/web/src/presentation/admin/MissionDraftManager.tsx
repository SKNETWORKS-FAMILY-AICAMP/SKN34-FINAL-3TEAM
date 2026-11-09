import { useState } from 'react'
import { useNavigate } from 'react-router'
import type { AchievementStandard, MissionDraft, MissionDraftRequest } from '../../domain/admin/missionStandards.ts'
import {
  discardableDraft, draftCheckLabels, draftReasonLabels, draftRequestErrors, draftStatusLabels, elementCodeLabel,
} from '../../domain/admin/missionStandards.ts'
import { missingFieldLabel } from '../../domain/admin/operations.ts'
import { inputLabels, thinkingLabels } from '../../domain/classroom.ts'
import { adminApi } from '../../data/admin/api.ts'
import { useAdminMutation, useAdminQuery } from '../../data/admin/queries.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { Badge, Empty, Panel } from './AdminUi.tsx'
import { date } from './adminFormatting.ts'
import { StandardPicker } from './StandardPicker.tsx'

/** 생성 중인 초안이 있으면 5초마다 다시 조회 (생성 1회 15~70초, 주기 작업 10초, state-diagram 3.4) */
const POLL_MS = 5_000
const generating = (items: MissionDraft[] | undefined) => items?.some((d) => d.status === 'GENERATING') ? POLL_MS : false

/** 관리자 미션 초안: 요청 → 목록 → 상세 → 채택(미션 편집으로)·버리기 (FN-ADM-20, api-spec 2.8, #356) */
export function MissionDraftManager() {
  const [status, setStatus] = useState(''), [page, setPage] = useState(0), [selected, setSelected] = useState<string | null>(null)
  const list = useAdminQuery(['mission-drafts', status, page], (signal) => adminApi.drafts({ status, page: String(page), size: '20' }, signal),
    true, (data) => generating(data?.items))
  const rows = list.error ? [] : list.data?.items ?? []
  return (
    <>
      <h2>미션 초안</h2>
      <p>
        성취기준·성취수준을 고르면 LLM이 초안을 만들고 자동 검사합니다. 검사 통과(READY)는 공개 승인이 아니며, 채택한 미션은 사람
        검토·게시를 거칩니다.
      </p>
      <DraftRequestForm onRequested={(d) => { setStatus(''); setPage(0); setSelected(d.draftId) }} />
      <div className="ad-split">
        <Panel title="초안 목록" action={
          <label>
            상태{' '}
            <select aria-label="초안 상태 필터" value={status} onChange={(e) => { setStatus(e.target.value); setPage(0) }}>
              <option value="">전체</option>
              {Object.entries(draftStatusLabels).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
        }>
          <QueryFeedback query={list} />
          <div className="ad-table-wrap">
            <table className="ad-table">
              <thead><tr><th>요청 시각</th><th>성취기준</th><th>상태</th><th className="num">시도</th><th>확인</th></tr></thead>
              <tbody>
                {rows.map((d) => (
                  <tr key={d.draftId} className={d.draftId === selected ? 'is-selected' : ''}>
                    <td>{date(d.createdAt)}<small>{thinkingLabels[d.input.thinkingType]} · 초{d.input.gradeMin}~{d.input.gradeMax}</small></td>
                    <td>{d.input.standardCodes.join(', ')}</td>
                    <td><Badge active={d.status === 'READY'}>{draftStatusLabels[d.status] ?? d.status}</Badge></td>
                    <td className="num">{d.attempts}/{d.maxAttempts}</td>
                    <td><button aria-label={`${date(d.createdAt)} 초안 열기`} onClick={() => setSelected(d.draftId)}>열기</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {list.data && !list.error && !rows.length && <Empty>조건에 맞는 초안이 없습니다.</Empty>}
          {list.data && !list.error && (
            <div className="ws-actions" aria-label="초안 목록 페이지">
              <button className="cj-secondary" disabled={page <= 0} onClick={() => setPage(page - 1)}>이전 페이지</button>
              <span>{page + 1}쪽 · 총 {list.data.totalElements}개</span>
              <button className="cj-secondary" disabled={(page + 1) * list.data.size >= list.data.totalElements} onClick={() => setPage(page + 1)}>다음 페이지</button>
            </div>
          )}
        </Panel>
        {selected ? <DraftDetail key={selected} id={selected} /> : <Panel title="초안 상세"><Empty>초안을 열어 주세요.</Empty></Panel>}
      </div>
    </>
  )
}

function DraftRequestForm({ onRequested }: { onRequested: (d: MissionDraft) => void }) {
  const [req, setReq] = useState<MissionDraftRequest>({
      standardCodes: [], achievementLevels: null, thinkingType: 'ANALYZE', gradeMin: 3, gradeMax: 4, inputType: 'NARRATIVE',
    }),
    [rows, setRows] = useState<Record<string, AchievementStandard>>({}),
    [errors, setErrors] = useState<string[]>([]),
    [notice, setNotice] = useState(''),
    request = useAdminMutation((body: MissionDraftRequest) => adminApi.requestDraft(body))
  return (
    <Panel title="새 초안 요청">
      <form className="ws-form" onSubmit={(e) => {
        e.preventDefault()
        const body = { ...req, achievementLevels: Object.keys(req.achievementLevels ?? {}).length ? req.achievementLevels : null }
        const found = draftRequestErrors(body, rows)
        setErrors(found); setNotice('')
        if (found.length) return
        void request.mutateAsync(body).then((d) => {
          setNotice('초안을 요청했습니다. 생성·자동 검사에 1분 안팎 걸리며 목록에서 상태가 바뀝니다.')
          onRequested(d)
        }).catch(() => {})
      }}>
        <StandardPicker codes={req.standardCodes} levels={req.achievementLevels ?? {}} gradeMin={req.gradeMin} gradeMax={req.gradeMax} subject=""
          onChange={(standardCodes, achievementLevels, known) => { setReq({ ...req, standardCodes, achievementLevels }); setRows(known) }} />
        <div className="ws-grid">
          <label>
            생각 유형
            <select aria-label="초안 생각 유형" value={req.thinkingType}
              onChange={(e) => setReq({ ...req, thinkingType: e.target.value as MissionDraftRequest['thinkingType'] })}>
              {Object.entries(thinkingLabels).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label>
            입력 방식
            <select aria-label="초안 입력 방식" value={req.inputType}
              onChange={(e) => setReq({ ...req, inputType: e.target.value as MissionDraftRequest['inputType'] })}>
              {Object.entries(inputLabels).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label>
            최소 학년
            <input aria-label="초안 최소 학년" type="number" min={3} max={6} value={req.gradeMin}
              onChange={(e) => setReq({ ...req, gradeMin: Number(e.target.value) })} />
          </label>
          <label>
            최대 학년
            <input aria-label="초안 최대 학년" type="number" min={3} max={6} value={req.gradeMax}
              onChange={(e) => setReq({ ...req, gradeMax: Number(e.target.value) })} />
          </label>
        </div>
        {errors.length > 0 && <ul role="alert" aria-label="초안 요청 전 확인">{errors.map((e) => <li key={e}>{e}</li>)}</ul>}
        <button className="cj-primary" disabled={request.isPending}>초안 요청</button>
        <p role="status">{notice}</p>
        <ErrorNotice error={request.error} />
      </form>
    </Panel>
  )
}

function DraftDetail({ id }: { id: string }) {
  const navigate = useNavigate(), [notice, setNotice] = useState('')
  const q = useAdminQuery(['mission-draft', id], (signal) => adminApi.draft(id, signal), true, (d) => generating(d ? [d] : undefined))
  const adopt = useAdminMutation(() => adminApi.adoptDraft(id)), discard = useAdminMutation(() => adminApi.discardDraft(id))
  const d = q.error ? undefined : q.data, g = d?.draft
  return (
    <Panel title="초안 상세">
      <QueryFeedback query={q} />
      {d && (
        <>
          <dl className="ad-facts">
            <dt>상태</dt><dd>{draftStatusLabels[d.status] ?? d.status}{d.status === 'GENERATING' && ' · 자동으로 다시 확인합니다'}</dd>
            <dt>시도 횟수</dt><dd>{d.attempts}/{d.maxAttempts}회 (AI 호출 실패 포함)</dd>
            <dt>성취기준</dt><dd>{d.input.standardCodes.map((c) => `${c}${d.input.achievementLevels?.[c] ? ` (성취수준 ${d.input.achievementLevels[c]})` : ''}`).join(', ')}</dd>
            <dt>미션 조건</dt><dd>{thinkingLabels[d.input.thinkingType]} · {inputLabels[d.input.inputType]} · 초{d.input.gradeMin}~{d.input.gradeMax}</dd>
            {d.failureCode && <><dt>실패 코드</dt><dd>{draftReasonLabels[d.failureCode] ?? d.failureCode} ({d.failureCode})</dd></>}
            <dt>생성 버전</dt><dd>프롬프트 {d.versions.prompt ?? '—'} · 모델 {d.versions.model ?? '—'}</dd>
            <dt>요청 시각</dt><dd>{date(d.createdAt)} · 갱신 {date(d.updatedAt)}</dd>
          </dl>
          {d.checkResults.length > 0 && (
            <section aria-label="검사 실패 사유">
              <h3>검사 실패 사유</h3>
              <ul>
                {d.checkResults.map((r) => (
                  <li key={r.attempt}>
                    {r.attempt}회차 · {r.failures.map((f) => `${draftCheckLabels[f.check] ?? f.check}: ${failureReason(f.check, f.reason)}`).join(' / ')}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {d.status === 'CHECK_FAILED' && <p role="note">시도 상한까지 검사를 통과하지 못했습니다. 버리고 새 초안을 요청하세요.</p>}
          {d.status === 'FAILED' && <p role="note">AI 호출이 실패해 초안을 만들지 못했습니다. 버리고 새 초안을 요청하세요.</p>}
          {g && (
            <section aria-label="초안 내용">
              <h3>{d.status === 'READY' || d.status === 'ADOPTED' ? '초안 내용' : '마지막 초안 (검사 통과 전)'}</h3>
              <p><strong>{g.title}</strong></p>
              <p>질문 · {g.question}</p>
              {g.guide && <p>안내 · {g.guide}</p>}
              {g.sceneNote && <p>장면 메모 · {g.sceneNote} (미션에 저장되지 않음)</p>}
              {g.choices?.length ? <p>선택 항목 · {g.choices.map((c) => c.label).join(', ')}</p> : null}
              {g.categories?.length ? <p>분류 그룹 · {g.categories.map((c) => c.label).join(', ')}</p> : null}
              <ul aria-label="초안 판정 요소">
                {g.elements.map((e) => (
                  <li key={e.code}>{e.code} · {e.label || elementCodeLabel(e.code)}{e.standardCode ? ` · ${e.standardCode}` : ''} — {e.description}</li>
                ))}
              </ul>
              {g.exampleAnswer && <p>예시 답 · {g.exampleAnswer}</p>}
              {g.hints.length > 0 && <p>생각 열기 질문 · {g.hints.join(' / ')}</p>}
              {g.forbiddenTerms.length > 0 && <p>금지어 · {g.forbiddenTerms.join(', ')}</p>}
            </section>
          )}
          <div className="ws-actions">
            {d.status === 'READY' && (
              <button className="cj-primary" disabled={adopt.isPending}
                onClick={() => void adopt.mutateAsync(undefined).then((m) => navigate(`/admin/missions?missionId=${encodeURIComponent(m.missionId)}`)).catch(() => {})}>
                채택해 미션 편집
              </button>
            )}
            {d.status === 'ADOPTED' && d.missionId && (
              <button className="cj-secondary" onClick={() => navigate(`/admin/missions?missionId=${encodeURIComponent(d.missionId!)}`)}>채택한 미션 열기</button>
            )}
            {discardableDraft(d.status) && (
              <button className="cj-secondary" disabled={discard.isPending}
                onClick={() => void discard.mutateAsync(undefined).then(() => setNotice('초안을 버렸습니다.')).catch(() => {})}>
                버리기
              </button>
            )}
          </div>
          <p role="status">{notice}</p>
          <ErrorNotice error={adopt.error ?? discard.error} />
        </>
      )}
    </Panel>
  )
}
/** learning 검사(STANDARD_CODE·ELEMENT_CODE·SHAPE)는 게시 누락 코드, 그 밖에는 ai 사유·실패 코드 */
function failureReason(check: string, reason: string) {
  if (['STANDARD_CODE', 'ELEMENT_CODE', 'SHAPE'].includes(check)) return missingFieldLabel(reason)
  return draftReasonLabels[reason] ?? reason
}
