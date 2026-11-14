import { useState } from 'react'
import { useSearchParams } from 'react-router'
import type { AdminMission, MissionVersion, Rubric } from '../../domain/admin/operations.ts'
import { missingFieldLabel, missingMissionFields, rubricSaveErrors } from '../../domain/admin/operations.ts'
import type { ElementKind } from '../../domain/admin/missionStandards.ts'
import {
  answerCodeFor, answerKeyInputs, commonElementsOf, defaultCode, elementCodeLabel, elementKind, elementKindLabels,
  isAnswerCode, kindsFor, nextUniqueCode, standardElements,
} from '../../domain/admin/missionStandards.ts'
import { StandardPicker } from './StandardPicker.tsx'
import { AnswerKeyFields } from './AnswerKeyFields.tsx'
import { ApiError } from '../../data/apiClient.ts'
import { missionLabels } from '../../domain/admin/operations.ts'
import { inputLabels, thinkingLabels, blankAnswer } from '../../domain/classroom.ts'
import type { AnswerContent } from '../../domain/classroom.ts'
import { adminApi } from '../../data/admin/api.ts'
import { useAdminQuery, useAdminMutation, useStandardsByCodes } from '../../data/admin/queries.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { MissionScene } from '../student/MissionScene.tsx'
import { AnswerFields } from '../student/StudentWorkPage.tsx'
export function MissionManager() {
  const [params, setParams] = useSearchParams(),
    filters = {
      status: params.get('status') ?? '',
      grade: params.get('grade') ?? '',
      thinkingType: params.get('thinkingType') ?? '',
      page: params.get('page') ?? '0',
    },
    q = useAdminQuery(['missions', filters], (signal) => adminApi.missions(filters, signal)),
    // 열린 미션은 URL에 둠: 초안 채택 뒤 /admin/missions?missionId=… 로 바로 편집 화면을 엶 (#356)
    id = params.get('missionId'),
    [creating, setCreating] = useState(false)
  function setId(missionId: string | null) {
    const next = new URLSearchParams(params)
    if (missionId) next.set('missionId', missionId)
    else next.delete('missionId')
    setParams(next)
  }
  function filter(key: string, value: string) {
    const next = new URLSearchParams(params)
    next.set(key, value)
    if (key !== 'page') next.set('page', '0')
    setParams(next)
  }
  return (
    <>
      <h2>미션 관리</h2>
      <p>수정하면 새 버전이 생깁니다. 기존 학습은 시작 당시 미션·기준표를 유지합니다.</p>
      <div className="ws-toolbar">
        <label>
          운영 상태
          <select
            aria-label="미션 운영 상태"
            value={filters.status}
            onChange={(e) => filter('status', e.target.value)}
          >
            <option value="">전체</option>
            {Object.entries(missionLabels).map(([v, l]) => (
              <option value={v} key={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label>
          학년
          <select
            aria-label="미션 학년 필터"
            value={filters.grade}
            onChange={(e) => filter('grade', e.target.value)}
          >
            <option value="">전체</option>
            {[3, 4, 5, 6].map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
        </label>
        <label>
          생각 유형
          <select
            aria-label="생각 유형 필터"
            value={filters.thinkingType}
            onChange={(e) => filter('thinkingType', e.target.value)}
          >
            <option value="">전체</option>
            {Object.entries(thinkingLabels).map(([v, l]) => (
              <option value={v} key={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <button className="cj-primary" onClick={() => setCreating(true)}>
          새 미션 작성
        </button>
      </div>
      <QueryFeedback query={q} />
      {q.data && !q.error && (
        <>
          <p>{q.data.counts.map((c) => `${missionLabels[c.status]} ${c.count}개`).join(' · ')}</p>
          <div className="ws-stack">
            {!q.data.items.length && <p>조건에 맞는 미션이 없습니다.</p>}
            {q.data.items.map((m) => (
              <article className="ws-card" key={m.missionId}>
                <h3>{m.versions.at(-1)!.title}</h3>
                <p>
                  {missionLabels[m.status]} · 초{m.versions.at(-1)!.gradeMin}~
                  {m.versions.at(-1)!.gradeMax} · {thinkingLabels[m.versions.at(-1)!.thinkingType]}
                </p>
                <button className="cj-secondary" onClick={() => setId(m.missionId)}>
                  미션 편집·검토
                </button>
              </article>
            ))}
          </div>
        </>
      )}
      {q.data && !q.error && <div className="ws-actions" aria-label="미션 목록 페이지">
        <button className="cj-secondary" disabled={q.data.page <= 0}
          onClick={() => filter('page', String(q.data!.page - 1))}>이전 페이지</button>
        <span>{q.data.page + 1}쪽 · 총 {q.data.totalElements}개</span>
        <button className="cj-secondary" disabled={(q.data.page + 1) * q.data.size >= q.data.totalElements}
          onClick={() => filter('page', String(q.data!.page + 1))}>다음 페이지</button>
      </div>}
      {creating && (
        <Modal title="새 미션 작성" onClose={() => setCreating(false)}>
          <MissionForm
            onSaved={(m) => {
              setCreating(false)
              setId(m.missionId)
            }}
          />
        </Modal>
      )}
      {id && <MissionDetail id={id} onClose={() => setId(null)} />}
    </>
  )
}
const defaults: Omit<MissionVersion, 'version' | 'createdAt'> = {
  title: '',
  subject: '과학',
  gradeMin: 3,
  gradeMax: 4,
  thinkingType: 'ANALYZE',
  inputType: 'NARRATIVE',
  question: '',
  guide: '',
  answerUnit: null,
  inputTemplate: [],
  sceneUri: '',
  staticSceneUri: '',
  achievementStandards: [],
  achievementLevels: null,
}
function MissionForm({
  mission,
  onSaved,
}: {
  mission?: AdminMission
  onSaved: (m: AdminMission) => void
}) {
  const [form, setForm] = useState(mission?.versions.find((v) => v.version === mission.currentVersion) ?? defaults),
    [demoOnly, setDemoOnly] = useState(mission?.demoOnly ?? true),
    [choices, setChoices] = useState(
      form.choices?.map((c) => `${c.id}|${c.label}`).join('\n') ?? '',
    ),
    [categories, setCategories] = useState(
      form.categories?.map((c) => `${c.id}|${c.label}`).join('\n') ?? '',
    ),
    save = useAdminMutation(() =>
      adminApi.save(
        { ...form, demoOnly, choices: parseOptions(choices), categories: parseOptions(categories),
          achievementLevels: levelsOf(form.achievementStandards, form.achievementLevels) },
        mission?.missionId,
      ),
    )
  function value<K extends keyof typeof form>(key: K, v: (typeof form)[K]) {
    setForm({ ...form, [key]: v })
  }
  return (
    <form
      className="ws-form"
      onSubmit={(e) => {
        e.preventDefault()
        void save
          .mutateAsync(undefined)
          .then(onSaved)
          .catch(() => {})
      }}
    >
      <label>
        미션 제목
        <input
          aria-label="미션 제목"
          required
          value={form.title}
          onChange={(e) => value('title', e.target.value)}
        />
      </label>
      <div className="ws-grid">
        <label>
          교과
          <input
            aria-label="교과"
            required
            value={form.subject}
            onChange={(e) => value('subject', e.target.value)}
          />
        </label>
        <label>
          생각 유형
          <select
            aria-label="미션 생각 유형"
            value={form.thinkingType}
            onChange={(e) =>
              value('thinkingType', e.target.value as MissionVersion['thinkingType'])
            }
          >
            {Object.entries(thinkingLabels).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label>
          최소 학년
          <input
            aria-label="최소 학년"
            type="number"
            min={3}
            max={6}
            value={form.gradeMin}
            onChange={(e) => value('gradeMin', Number(e.target.value))}
          />
        </label>
        <label>
          최대 학년
          <input
            aria-label="최대 학년"
            type="number"
            min={3}
            max={6}
            value={form.gradeMax}
            onChange={(e) => value('gradeMax', Number(e.target.value))}
          />
        </label>
      </div>
      <label>
        입력 방식
        <select
          aria-label="미션 입력 방식"
          value={form.inputType}
          onChange={(e) => value('inputType', e.target.value as MissionVersion['inputType'])}
        >
          {Object.entries(inputLabels).map(([v, l]) => (
            <option value={v} key={v}>
              {l}
            </option>
          ))}
        </select>
      </label>
      <label>
        질문
        <textarea
          aria-label="미션 질문"
          value={form.question}
          onChange={(e) => value('question', e.target.value)}
        />
      </label>
      <label>
        안내
        <textarea
          aria-label="미션 안내"
          value={form.guide ?? ''}
          onChange={(e) => value('guide', e.target.value)}
        />
      </label>
      {form.inputType === 'SOLUTION_STEPS' && <label>
        답 단위 (예: m²)
        <input aria-label="답 단위" value={form.answerUnit ?? ''} onChange={(e) => value('answerUnit', e.target.value)} />
      </label>}
      {['SOLUTION_STEPS', 'ESSAY'].includes(form.inputType) && <label>
        입력 틀 항목 이름 (줄별 입력)
        <textarea aria-label="입력 틀" value={(form.inputTemplate ?? []).join('\n')}
          onChange={(e) => value('inputTemplate', e.target.value.split('\n'))} />
      </label>}
      <StandardPicker
        codes={form.achievementStandards}
        levels={form.achievementLevels ?? {}}
        gradeMin={form.gradeMin}
        gradeMax={form.gradeMax}
        subject={form.subject}
        onChange={(achievementStandards, achievementLevels) => setForm({ ...form, achievementStandards, achievementLevels })}
      />
      <label>
        애니메이션 장면 URI
        <input
          aria-label="장면 URI"
          value={form.sceneUri ?? ''}
          onChange={(e) => value('sceneUri', e.target.value)}
        />
      </label>
      <label>
        정적 장면 URI
        <input
          aria-label="정적 장면 URI"
          value={form.staticSceneUri ?? ''}
          onChange={(e) => value('staticSceneUri', e.target.value)}
        />
      </label>
      <p>업로드 API는 아직 없습니다. 비워 두면 자체 제작 기본 장면을 사용합니다.</p>
      {['CHOICE', 'ORDERING', 'CLASSIFICATION'].includes(form.inputType) && (
        <label>
          선택 항목 (한 줄에 ID|표시명)
          <textarea
            aria-label="선택 항목"
            value={choices}
            onChange={(e) => setChoices(e.target.value)}
            placeholder="c1|첫 번째 선택"
          />
        </label>
      )}
      {form.inputType === 'CLASSIFICATION' && (
        <label>
          분류 그룹 (한 줄에 ID|표시명)
          <textarea
            aria-label="분류 그룹"
            value={categories}
            onChange={(e) => setCategories(e.target.value)}
          />
        </label>
      )}
      <label className="ws-check">
        <input type="checkbox" checked={demoOnly} onChange={(e) => setDemoOnly(e.target.checked)} />
        시연 전용 문항
      </label>
      <p>AI Hub 원문·답안·피드백을 등록하지 마세요.</p>
      <button className="cj-primary" disabled={save.isPending}>
        {mission ? '새 미션 버전 저장' : '미션 초안 저장'}
      </button>
      <ErrorNotice error={save.error} />
    </form>
  )
}
/** 고른 성취기준의 단계만 보냄(빠진 성취기준 단계는 버림), 없으면 null */
function levelsOf(codes: string[], levels: Record<string, string> | null | undefined) {
  const kept = Object.entries(levels ?? {}).filter(([code]) => codes.includes(code))
  return kept.length ? Object.fromEntries(kept) : null
}
function parseOptions(text: string) {
  return text
    .split('\n')
    .filter((v) => v.trim())
    .map((line) => {
      const [id, ...label] = line.split('|')
      return { id: id.trim(), label: label.join('|').trim() }
    })
}
function MissionDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useAdminQuery(['mission', id], (signal) => adminApi.mission(id, signal)),
    [preview, setPreview] = useState(false),
    [notice, setNotice] = useState(''),
    action = useAdminMutation((v: { action: string; data?: unknown }) =>
      adminApi.action(id, v.action, v.data),
    )
  const m = q.error ? undefined : q.data
  const current = m?.versions.find((v) => v.version === m.currentVersion)
  const standards = useStandardsByCodes(current?.achievementStandards ?? [])
  // 표 조회가 끝나야 표·학년군·단계 수까지 확인. 실패하면 서버 게시 검사(422)에 맡김
  const missing = m ? missingMissionFields(m, standards.error || standards.isFetching ? undefined : standards.data ?? {}) : []
  function run(a: string, data: unknown = {}) {
    void action
      .mutateAsync({ action: a, data })
      .then((r) => setNotice(`서버 응답 · ${missionLabels[r.status]}`))
      .catch(() => {})
  }
  return (
    <section className="ws-card">
      <div className="ws-actions">
        <h2>미션 상세·버전</h2>
        <button className="cj-secondary" onClick={onClose}>
          편집 닫기
        </button>
      </div>
      <QueryFeedback query={q} />
      {m && (
        <>
          <p>
            {m.source === 'LLM_DRAFT' ? 'LLM 초안 채택' : m.source === 'LLM_THEME' ? '테마 초안 채택' : '사람 작성'} · {missionLabels[m.status]} · 편집본 v{m.currentVersion} · 기준표 v
            {m.currentRubricVersion ?? '미등록'} · 학생 공개본 {m.publishedVersion ? `v${m.publishedVersion} / 기준표 v${m.publishedRubricVersion ?? '미등록'}` : '없음'}
          </p>
          {m.status === 'PUBLISHED' && <p role="note">
            학생에게는 미션 v{m.publishedVersion}·기준표 v{m.publishedRubricVersion ?? '미등록'} 공개본이 제공됩니다. 편집본·기준표 수정은 검토 요청 → 검토 → 게시 후 새 시도부터 적용됩니다.
          </p>}
          <details>
            <summary>미션·기준표 버전 이력</summary>
            {m.versions.map((v) => (
              <p key={v.version}>
                미션 v{v.version} · {v.title} · {v.createdAt}
              </p>
            ))}
            {m.rubrics.map((r) => (
              <p key={r.version}>
                기준표 v{r.version} · 요소 {r.elements.length}개
              </p>
            ))}
          </details>
          <div className="ws-grid">
            <section>
              <h3>내용 수정</h3>
              <MissionForm
                key={`v${m.currentVersion}`}
                mission={m}
                onSaved={() =>
                  setNotice('새 버전을 저장했습니다. 재검토·재게시 후 신규 시도부터 적용됩니다.')
                }
              />
            </section>
            <section>
              <h3>판정 기준표</h3>
              <RubricForm key={`v${m.currentVersion}-r${m.currentRubricVersion}`} mission={m} onSaved={() => setNotice('새 기준표 버전을 저장했습니다.')} />
            </section>
          </div>
          <section role="note" aria-label="검토 안내">
            <h3>검토 때 확인할 것</h3>
            <p>
              학년(미션 학년과 성취기준 학년군)·내용·행동(성취기준 문장의 동사)이 미션 질문과 맞는지 확인하세요.
              초안 자동 검사 통과만으로 공개하지 않습니다.
            </p>
            <ul>
              {current?.achievementStandards.map((code) => {
                const s = standards.data?.[code]
                return (
                  <li key={code}>
                    {code} · {s ? `${s.gradeBand} · ${s.statement}` : '성취기준 표에서 확인하지 못함'} · 성취수준{' '}
                    {current.achievementLevels?.[code] ?? '고르지 않음'}
                  </li>
                )
              })}
            </ul>
          </section>
          <div className="ws-actions">
            <button className="cj-secondary" onClick={() => setPreview(true)}>
              학생 화면 미리보기
            </button>
            <button
              className="cj-secondary"
              disabled={action.isPending || !m.currentRubricVersion}
              onClick={() =>
                run('review-request', {
                  missionVersion: m.currentVersion,
                  rubricVersion: m.currentRubricVersion,
                })
              }
            >
              검토 요청
            </button>
            {(m.status === 'REVIEW_REQUIRED' || m.status === 'PUBLISHED') && (
              <>
                <button
                  className="cj-secondary"
                  disabled={action.isPending}
                  onClick={() =>
                    run('review', {
                      missionVersion: m.currentVersion,
                      rubricVersion: m.currentRubricVersion,
                      result: 'APPROVED',
                      comment: '학년·내용·행동(성취기준 동사)·기준표·정답 공개 조건 확인',
                    })
                  }
                >
                  현재 버전 검토 승인
                </button>
                <button
                  className="cj-secondary"
                  disabled={action.isPending}
                  onClick={() =>
                    run('review', {
                      missionVersion: m.currentVersion,
                      rubricVersion: m.currentRubricVersion,
                      result: 'CHANGES_REQUESTED',
                      comment: '콘텐츠 보완 후 재검토 요청',
                    })
                  }
                >
                  보완 요청
                </button>
              </>
            )}
            <button
              className="cj-primary"
              disabled={action.isPending}
              onClick={() => run('publish')}
            >
              게시
            </button>
            {m.status === 'PUBLISHED' && (
              <button
                className="cj-secondary ad-danger"
                disabled={action.isPending}
                onClick={() => run('unpublish')}
              >
                신규 제공 중단
              </button>
            )}
          </div>
          {missing.length > 0 && <div><h3>게시 전 확인할 항목</h3>
            <ul aria-label="게시 전 확인">{missing.map((code) => <li key={code}>{missingFieldLabel(code)}</li>)}</ul>
          </div>}
          <p>
            검토·게시는 CONTENT 권한 1인도 가능합니다. 제공 중단 후에도 진행 중 학습은 시작 당시
            버전으로 계속됩니다.
          </p>
          {m.reviews.map((r, i) => (
            <p key={i}>
              검토 · 미션 v{r.missionVersion} / 기준표 v{r.rubricVersion} · {r.result} · {r.comment}
            </p>
          ))}
        </>
      )}
      <p role="status">{notice}</p>
      <ErrorNotice error={action.error instanceof ApiError && action.error.problem.missingFields ?
        new ApiError({ ...action.error.problem, missingFields: action.error.problem.missingFields.map(missingFieldLabel) }) : action.error} />
      {preview && (
        <Modal title="학생 화면 미리보기" onClose={() => setPreview(false)}>
          <MissionPreview id={id} />
        </Modal>
      )}
    </section>
  )
}
function RubricForm({ mission, onSaved }: { mission: AdminMission; onSaved: () => void }) {
  const [r, setR] = useState<Omit<Rubric, 'version'>>(
      mission.rubrics.find((r) => r.version === mission.currentRubricVersion) ?? {
        elements: [],
        answerKey: null,
        exampleAnswer: '',
        forbiddenTerms: [],
        hints: [],
        keywords: [],
        essayType: null,
      },
    ),
    save = useAdminMutation(() => adminApi.rubric(mission.missionId, { ...r, answerKey: ['NARRATIVE', 'ESSAY'].includes(mission.versions.find((v) => v.version === mission.currentVersion)!.inputType) ? null : r.answerKey })),
    [errors, setErrors] = useState<string[]>([])
  const version = mission.versions.find((v) => v.version === mission.currentVersion)!
  const codes = r.elements.map((e) => e.code)
  /** 요소 종류·code를 고르면 정답 요소는 연결 성취기준을 비우고, 이름·설명이 비어 있으면 표준 요소 문구로 채움 */
  function pickCode(i: number, code: string) {
    const e = r.elements[i], std = standardElements.find((s) => s.code === code)
    const patch = {
      code,
      ...(isAnswerCode(code) ? { standardCode: null, label: e.label || elementCodeLabel(code) } : {}),
      ...(std ? { label: e.label || std.label, description: e.description || std.description } : {}),
    }
    setR({ ...r, elements: r.elements.map((v, j) => (i === j ? { ...v, ...patch } : v)) })
  }
  return (
    <form
      className="ws-form"
      onSubmit={(e) => {
        e.preventDefault()
        const found = rubricSaveErrors(r.elements)
        setErrors(found)
        if (found.length) return
        void save
          .mutateAsync(undefined)
          .then(onSaved)
          .catch(() => {})
      }}
    >
      {r.elements.map((element, i) => (
        <section className="ws-card ws-form" key={i}>
          <ElementCodeFields
            index={i}
            code={element.code}
            standardCode={element.standardCode ?? null}
            others={codes.filter((_, j) => j !== i)}
            version={version}
            onCode={(code) => pickCode(i, code)}
            onStandard={(standardCode) => setR({ ...r, elements: r.elements.map((v, j) => (i === j ? { ...v, standardCode } : v)) })}
          />
          <label>
            요소 {i + 1} 이름
            <input
              aria-label={`요소 ${i + 1} 이름`}
              value={element.label}
              required
              onChange={(e) =>
                setR({
                  ...r,
                  elements: r.elements.map((v, j) =>
                    i === j ? { ...v, label: e.target.value } : v,
                  ),
                })
              }
            />
          </label>
          <label>
            설명
            <input
              aria-label={`요소 ${i + 1} 설명`}
              value={element.description ?? ''}
              onChange={(e) =>
                setR({
                  ...r,
                  elements: r.elements.map((v, j) =>
                    i === j ? { ...v, description: e.target.value } : v,
                  ),
                })
              }
            />
          </label>
          <label>
            배점
            <input
              aria-label={`요소 ${i + 1} 배점`}
              type="number"
              min={1}
              value={element.points}
              onChange={(e) =>
                setR({
                  ...r,
                  elements: r.elements.map((v, j) =>
                    i === j ? { ...v, points: Number(e.target.value) } : v,
                  ),
                })
              }
            />
          </label>
          <label>
            흔한 오답 (줄별)
            <textarea
              aria-label={`요소 ${i + 1} 흔한 오답`}
              value={element.commonErrors.join('\n')}
              onChange={(e) =>
                setR({
                  ...r,
                  elements: r.elements.map((v, j) =>
                    i === j ? { ...v, commonErrors: e.target.value.split('\n') } : v,
                  ),
                })
              }
            />
          </label>
          <label className="ws-check">
            <input
              type="checkbox"
              checked={element.goodThought}
              onChange={(e) =>
                setR({
                  ...r,
                  elements: r.elements.map((v, j) =>
                    i === j ? { ...v, goodThought: e.target.checked } : v,
                  ),
                })
              }
            />
            들어가면 좋은 생각
          </label>
          <p>
            판정 검증 상태:{' '}
            {element.judgeVerified ? '검증 통과' : '미검증 · 평가 전 임의 승인 불가'}
          </p>
          <button
            type="button"
            className="cj-secondary ad-danger"
            onClick={() => setR({ ...r, elements: r.elements.filter((_, j) => j !== i) })}
          >
            이 요소 삭제
          </button>
        </section>
      ))}
      <button
        type="button"
        className="cj-secondary"
        onClick={() =>
          setR({
            ...r,
            elements: [...r.elements, newElement(version, codes)],
          })
        }
      >
        기준표 요소 추가
      </button>
      <p>
        모든 입력 방식에 기준표 요소가 필요합니다. 고르기·순서·분류는 정답 요소(ANSWER_KEY) 하나만, 풀이 단계는 최종 답(FINAL_ANSWER) 외 풀이 요소를
        포함합니다. 따져 보기 논술은 주장·근거·다른 관점 세 요소를 모두 둡니다.
      </p>
      <AnswerKeyFields version={version} value={r.answerKey} onChange={(answerKey) => setR({ ...r, answerKey })} />
      <label>
        예시 답
        <textarea
          aria-label="예시 답"
          value={r.exampleAnswer ?? ''}
          onChange={(e) => setR({ ...r, exampleAnswer: e.target.value })}
        />
      </label>
      <label>
        생각 열기 질문 (줄별)
        <textarea
          aria-label="생각 열기 질문"
          value={r.hints.join('\n')}
          onChange={(e) => setR({ ...r, hints: e.target.value.split('\n').filter(Boolean) })}
        />
      </label>
      <label>
        금지어 (줄별)
        <textarea
          aria-label="금지어"
          value={r.forbiddenTerms.join('\n')}
          onChange={(e) =>
            setR({ ...r, forbiddenTerms: e.target.value.split('\n').filter(Boolean) })
          }
        />
      </label>
      {/* #69 교차 확인 입력은 이 화면에서 편집하지 않고 저장 때 그대로 유지한다 (#306). */}
      <p>
        교차 확인 입력 · 핵심어 {r.keywords?.length ?? 0}개 · 글 종류 {r.essayType ?? '없음'} (저장해도 유지됩니다)
      </p>
      {errors.length > 0 && (
        <ul role="alert" aria-label="기준표 저장 전 확인">
          {errors.map((e) => <li key={e}>{e}</li>)}
        </ul>
      )}
      <button className="cj-primary" disabled={save.isPending}>
        새 기준표 버전 저장
      </button>
      <ErrorNotice error={save.error} />
    </form>
  )
}
/** 새 요소: 고르기·순서·분류는 정답 요소, 그 밖에는 아직 안 쓴 유형 공통 요소, 다 쓰면 성취기준 고유 요소 */
function newElement(version: MissionVersion, codes: string[]): Rubric['elements'][number] {
  const common = answerKeyInputs.includes(version.inputType) ? undefined : commonElementsOf(version.thinkingType).find((e) => !codes.includes(e.code))
  const code = answerKeyInputs.includes(version.inputType) ? answerCodeFor(version.inputType)! : common?.code ?? nextUniqueCode(codes)
  return {
    code, label: common?.label ?? (isAnswerCode(code) ? elementCodeLabel(code) : ''), description: common?.description ?? '',
    points: 1, commonErrors: [], goodThought: true, judgeVerified: false, standardCode: null,
  }
}
/** 요소 종류 → code → 연결 성취기준 (FN 1.5 표준 요소, #262·#356) */
function ElementCodeFields({ index, code, standardCode, others, version, onCode, onStandard }: {
  index: number
  code: string
  standardCode: string | null
  others: string[]
  version: MissionVersion
  onCode: (code: string) => void
  onStandard: (code: string | null) => void
}) {
  const kind = elementKind(code), n = index + 1
  const common = commonElementsOf(version.thinkingType)
  const answer = answerCodeFor(version.inputType)
  return (
    <>
      <label>
        요소 {n} 종류
        <select aria-label={`요소 ${n} 종류`} value={kind ?? ''}
          onChange={(e) => onCode(defaultCode(e.target.value as ElementKind, version.thinkingType, version.inputType, others))}>
          {!kind && <option value="">확인 필요 (옛 code: {code || '없음'})</option>}
          {kind && !kindsFor(version.inputType).includes(kind) && <option value={kind}>{elementKindLabels[kind]} (이 입력 방식에 맞지 않음)</option>}
          {kindsFor(version.inputType).map((k) => <option key={k} value={k}>{elementKindLabels[k]}</option>)}
        </select>
      </label>
      {kind === 'COMMON' ? (
        <label>
          요소 {n} 코드
          <select aria-label={`요소 ${n} 코드`} value={code} onChange={(e) => onCode(e.target.value)}>
            {!common.some((e) => e.code === code) && <option value={code}>{code} (다른 생각 유형)</option>}
            {common.map((e) => (
              <option key={e.code} value={e.code} disabled={others.includes(e.code)}>{e.code} · {e.label}</option>
            ))}
          </select>
          <small>{standardElements.find((e) => e.code === code)?.description}</small>
        </label>
      ) : kind === 'ANSWER' ? (
        <label>
          요소 {n} 코드
          <select aria-label={`요소 ${n} 코드`} value={code} onChange={(e) => onCode(e.target.value)}>
            {code !== answer && <option value={code}>{code} (이 입력 방식에 맞지 않음)</option>}
            {answer && <option value={answer}>{answer} · {elementCodeLabel(answer)}</option>}
          </select>
        </label>
      ) : (
        <label>
          요소 {n} 코드 {kind === 'UNIQUE' ? '(e+숫자, 예: e1)' : ''}
          <input aria-label={`요소 ${n} 코드`} value={code} onChange={(e) => onCode(e.target.value.trim())} />
        </label>
      )}
      <label>
        요소 {n} 연결 성취기준
        <select aria-label={`요소 ${n} 연결 성취기준`} value={standardCode ?? ''} disabled={kind === 'ANSWER'}
          onChange={(e) => onStandard(e.target.value || null)}>
          <option value="">{kind === 'ANSWER' ? '정답 요소는 비움' : '연결 안 함'}</option>
          {standardCode && !version.achievementStandards.includes(standardCode) && <option value={standardCode}>{standardCode} (미션 성취기준 아님)</option>}
          {version.achievementStandards.filter((c) => c.trim()).map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </label>
    </>
  )
}
function MissionPreview({ id }: { id: string }) {
  const q = useAdminQuery(['preview', id], (signal) => adminApi.preview(id, signal)),
    [answer, setAnswer] = useState<AnswerContent | null>(null)
  return (
    <>
      <QueryFeedback query={q} />
      {q.data && !q.error && (
        <>
          <p>
            미션 v{q.data.missionVersion} · 기준표 v{q.data.rubricVersion ?? '없음'} · 제출·저장하지
            않는 미리보기
          </p>
          <h3>{q.data.mission.title}</h3>
          <MissionScene mission={q.data.mission} />
          <p>{q.data.mission.question}</p>
          <AnswerFields
            mission={q.data.mission}
            answer={answer ?? blankAnswer(q.data.mission.inputType)}
            onChange={setAnswer}
          />
        </>
      )}
    </>
  )
}
