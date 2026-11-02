import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import type { Attempt } from '../../domain/classroom.ts'
import { saveSelfAssessment } from '../../data/classroom/learningApi.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'

export function SelfAssessmentPanel({ attempt, onBusyChange }: { attempt: Attempt; onBusyChange: (busy: boolean) => void }) {
  const [checks, setChecks] = useState<Record<string, boolean>>({})
  const [dirty, setDirty] = useState(false)
  const save = useMutation({
    mutationFn: () => saveSelfAssessment(attempt.attemptId,
      Object.entries(checks).map(([elementId, checked]) => ({ elementId, checked }))),
    onSuccess: (rows) => {
      setChecks(Object.fromEntries(rows.filter((e) => e.selfChecked !== null).map((e) => [e.elementId, e.selfChecked as boolean])))
      setDirty(false)
    },
  })
  useEffect(() => { onBusyChange(save.isPending); return () => onBusyChange(false) }, [save.isPending, onBusyChange])
  if (!attempt.finishedAt || attempt.status === 'COMPLETED' || !attempt.checklist?.length) return null
  return <section className="ux-self-assessment" aria-label="내 답 돌아보기">
    <h3>내 답도 확인해 보세요.</h3>
    <p>내 답에 담았다고 생각하는 항목을 골라 주세요. 선생님 확인과 나란히 볼 수 있어요.</p>
    <div className="ux-checklist">
      {attempt.checklist.map((e) => <label className="ux-self-row" key={e.elementId}>
        <input type="checkbox" checked={checks[e.elementId] ?? false} disabled={save.isPending}
          onChange={(event) => { setChecks({ ...checks, [e.elementId]: event.target.checked }); setDirty(true) }} />
        {e.label}
      </label>)}
    </div>
    <button className="cj-secondary" disabled={save.isPending || !Object.keys(checks).length || !dirty}
      onClick={() => save.mutate()}>내 확인 저장</button>
    <ErrorNotice error={save.error} />
    {save.data && <><p role="status">{dirty ? '바꾼 항목은 다시 저장해 주세요.' : '내 확인을 저장했어요.'}</p>
      <div className="ux-assessment-comparison" role="region" aria-label="내 확인과 선생님 확인 비교">
        {save.data.map((e) => <div key={e.elementId} className="ux-assessment-result">
          <strong>{e.label}</strong>
          <span>내 확인: {e.selfChecked === null ? '선택하지 않았어요' : e.selfChecked ? '담았어요' : '아직이에요'}</span>
          <span>선생님 확인: {e.aiChecked ? '확인했어요' : '아직 확인하지 못했어요'}</span>
          {e.quote && <blockquote>{e.quote}</blockquote>}
        </div>)}
      </div></>}
  </section>
}
