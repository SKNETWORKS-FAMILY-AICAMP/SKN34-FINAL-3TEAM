import type { AnswerKey, MissionVersion } from '../../domain/admin/operations.ts'

export function AnswerKeyFields({ version, value, onChange }: {
  version: MissionVersion; value: AnswerKey | null | undefined; onChange: (value: AnswerKey) => void
}) {
  const choices = version.choices ?? []
  if (['NARRATIVE', 'ESSAY'].includes(version.inputType)) return null
  if (version.inputType === 'SOLUTION_STEPS') return <label>
    정답 (수만 입력)
    <span className="ux-answer-unit"><input aria-label="정답 수" inputMode="decimal"
      value={value?.finalAnswer ?? ''}
      onChange={(e) => onChange({ finalAnswer: e.target.value })} />
      {version.answerUnit && <span>{version.answerUnit}</span>}
    </span>
  </label>
  if (version.inputType === 'CLASSIFICATION') {
    const assignments = value?.assignments ?? []
    return <fieldset><legend>정답 분류</legend>
      {choices.map((choice) => <label key={choice.id}>{choice.label}
        <select aria-label={`정답 분류 ${choice.label}`}
          value={assignments.find((a) => a.choiceId === choice.id)?.categoryId ?? ''}
          onChange={(e) => onChange({ assignments: [...assignments.filter((a) => a.choiceId !== choice.id),
            ...(e.target.value ? [{ choiceId: choice.id, categoryId: e.target.value }] : [])] })}>
          <option value="">그룹 선택</option>
          {version.categories?.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
        </select>
      </label>)}
    </fieldset>
  }
  const ids = value?.choiceIds ?? []
  if (version.inputType === 'ORDERING') return <fieldset><legend>정답 순서</legend>
    <p>정답 순서대로 항목을 누르세요. 선택한 항목을 다시 누르면 순서에서 빠집니다.</p>
    <div className="ws-actions">{choices.map((choice) => <button type="button" className="cj-secondary"
      key={choice.id} aria-pressed={ids.includes(choice.id)} onClick={() => onChange({
        choiceIds: ids.includes(choice.id) ? ids.filter((id) => id !== choice.id) : [...ids, choice.id],
      })}>{ids.includes(choice.id) ? `${ids.indexOf(choice.id) + 1}. ` : ''}{choice.label}</button>)}</div>
    <ol aria-label="정답 순서">{ids.map((id) => <li key={id}>{choices.find((c) => c.id === id)?.label ?? id}</li>)}</ol>
    <button type="button" className="cj-secondary" onClick={() => onChange({ choiceIds: [] })}>정답 순서 초기화</button>
  </fieldset>
  return <fieldset><legend>정답 선택</legend>{choices.map((choice) => <label className="ws-check" key={choice.id}>
    <input type="radio" name="answer-key-choice" checked={ids.includes(choice.id)}
      onChange={() => onChange({ choiceIds: [choice.id] })} />{choice.label}
  </label>)}</fieldset>
}
