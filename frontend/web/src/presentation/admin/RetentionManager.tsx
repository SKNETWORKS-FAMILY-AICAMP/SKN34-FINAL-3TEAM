import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { adminApi } from '../../data/admin/api.ts'
import { adminRetentionApi as api } from '../../data/admin/retentionApi.ts'
import { useAdminMutation, useAdminQuery } from '../../data/admin/queries.ts'
import { ApiError } from '../../data/apiClient.ts'
import { thinkingLabels } from '../../domain/classroom.ts'
import { ALL_ITEM_SLOTS, DAY_LABELS, SLOT_LABELS, THEME_DAYS } from '../../domain/retention.ts'
import type { ItemSlot, ThemeDay } from '../../domain/retention.ts'
import {
  THEME_GRADE_LABELS,
  publishProblems,
  THEME_STATUS_LABELS,
} from '../../domain/admin/retention.ts'
import type { AdminLookItem, AdminWeeklyTheme, ThemeGrade } from '../../domain/admin/retention.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ThemeMotionPlayer } from '../common/ThemeMotionPlayer.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { Badge, Empty, Panel } from './AdminUi.tsx'
import { date } from './adminFormatting.ts'

const nextMonday = () => {
  const kst = new Date(Date.now() + 9 * 3600_000)
  kst.setUTCDate(kst.getUTCDate() + ((8 - kst.getUTCDay()) % 7 || 7))
  return kst.toISOString().slice(0, 10)
}

/**
 * 주간 테마 관리 (FN-ADM-22, CONTENT). 학년별 주 1개, 월~금 하루 한 문제(다섯 생각 유형 하나씩).
 * 게시 검사(게시 미션만·유형 1개씩·학년 맞음·같은 주 게시 1개)는 서버가 하고 실패 이유를 그대로 보인다.
 */
export function WeeklyThemeManager() {
  const [grade, setGrade] = useState(''), [status, setStatus] = useState('')
  const list = useAdminQuery(['weekly-themes', grade, status], (s) => api.themes({ grade, status }, s))
  const [params, setParams] = useSearchParams()
  const themeId = params.get('themeId') ?? ''
  const linked = useAdminQuery(['weekly-theme', themeId], signal => api.theme(themeId, signal), !!themeId && themeId !== 'new')
  const [local, setEditing] = useState<AdminWeeklyTheme | 'new' | null>(null)
  const editing = themeId === 'new' ? 'new' : local && local !== 'new' && local.themeId === themeId ? local : linked.data
  const selectId = (id: string | null) => { const next = new URLSearchParams(params); if (id) next.set('themeId', id); else next.delete('themeId'); setParams(next) }
  // 저장 뒤 편집 중인 테마가 바뀌어도 창을 다시 만들지 않게, 열 때마다 바뀌는 키를 따로 둔다.
  const [opened, setOpened] = useState(0)
  const open = (t: AdminWeeklyTheme | 'new') => {
    setEditing(t)
    selectId(t === 'new' ? 'new' : t.themeId)
    setOpened((n) => n + 1)
  }
  const rows = list.error ? [] : (list.data?.items ?? [])
  return (
    <div className="ad-two">
      <Panel title="주간 테마" action={<button onClick={() => open('new')}>새 테마</button>}>
        <div className="ad-toolbar">
          <label>
            학년
            <select aria-label="테마 학년" value={grade} onChange={(e) => setGrade(e.target.value)}>
              <option value="">전체</option>
              {Object.entries(THEME_GRADE_LABELS).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </label>
          <label>
            상태
            <select aria-label="테마 상태" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">전체</option>
              {Object.entries(THEME_STATUS_LABELS).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </label>
        </div>
        <QueryFeedback query={list} />
        <div className="ad-table-wrap">
          <table className="ad-table">
            <thead>
              <tr><th>주 시작</th><th>제목</th><th>학년</th><th>상태</th><th>관리</th></tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.themeId}>
                  <td>{t.weekStart}</td>
                  <td>{t.title}<small>수정 {date(t.updatedAt)}</small></td>
                  <td>{THEME_GRADE_LABELS[t.grade]}</td>
                  <td><Badge active={t.status === 'PUBLISHED'}>{THEME_STATUS_LABELS[t.status]}</Badge></td>
                  <td><button onClick={() => open(t)} aria-label={`${t.title} 테마 열기`}>열기</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {list.data && !list.error && !rows.length && <Empty>조건에 맞는 테마가 없습니다.</Empty>}
      </Panel>
      {themeId && themeId !== 'new' && <QueryFeedback query={linked} />}
      {editing && !linked.error && (
        <ThemeEditor
          key={`${themeId}:${opened}`}
          theme={editing === 'new' ? undefined : editing}
          onSaved={theme => { setEditing(theme); selectId(theme.themeId) }}
          onClose={() => { setEditing(null); selectId(null) }}
        />
      )}
    </div>
  )
}

function ThemeEditor({
  theme,
  onSaved,
  onClose,
}: {
  theme?: AdminWeeklyTheme
  onSaved: (t: AdminWeeklyTheme) => void
  onClose: () => void
}) {
  const [grade, setGrade] = useState<ThemeGrade>(theme?.grade ?? 'G3')
  const [weekStart, setWeekStart] = useState(theme?.weekStart ?? nextMonday())
  const [title, setTitle] = useState(theme?.title ?? ''), [intro, setIntro] = useState(theme?.intro ?? '')
  const [days, setDays] = useState<Record<ThemeDay, string>>(
    () => Object.fromEntries(THEME_DAYS.map((d) => [d, theme?.days.find((x) => x.day === d)?.missionId ?? ''])) as Record<ThemeDay, string>,
  )
  const [message, setMessage] = useState('')
  const missions = useAdminQuery(['missions', 'theme-picker'], (s) => adminApi.missions({ status: 'PUBLISHED' }, s))
  const choices = (missions.error ? [] : (missions.data?.items ?? [])).map((m) => {
    const v = m.versions.find((x) => x.version === (m.publishedVersion ?? m.currentVersion)) ?? m.versions.at(-1)
    return { id: m.missionId, title: v?.title ?? m.missionId, type: v?.thinkingType, grades: v ? `초${v.gradeMin}~${v.gradeMax}` : '' }
  })
  const input = () => ({ grade, weekStart, title: title.trim(), intro: intro.trim(), days: THEME_DAYS.map((day) => ({ day, missionId: days[day] })) })
  const save = useAdminMutation(() => (theme ? api.saveTheme(theme.themeId, input()) : api.createTheme(input())))
  const action = useAdminMutation((a: 'review-request' | 'publish' | 'unpublish') => api.themeAction(theme!.themeId, a))
  const types = THEME_DAYS.map((d) => choices.find((c) => c.id === days[d])?.type).filter(Boolean)
  const duplicateType = new Set(types).size !== types.length
  const problems = action.error instanceof ApiError ? publishProblems(action.error.problem) : []
  const run = (a: 'review-request' | 'publish' | 'unpublish', done: string) =>
    void action.mutateAsync(a).then((t) => { onSaved(t); setMessage(done) }).catch(() => {})
  return (
    <Panel title={theme ? '테마 수정·검토' : '새 테마 작성'} action={<button onClick={onClose}>닫기</button>}>
      <form
        className="ws-form"
        onSubmit={(e) => {
          e.preventDefault()
          void save.mutateAsync(undefined).then((t) => { onSaved(t); setMessage('테마를 저장했습니다. 게시 중 수정은 다시 검토를 거칩니다.') }).catch(() => {})
        }}
      >
        <div className="ad-two">
          <label>학년
            <select aria-label="학년" value={grade} onChange={(e) => setGrade(e.target.value as ThemeGrade)}>
              {Object.entries(THEME_GRADE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label>주 시작(월요일)
            <input type="date" aria-label="주 시작일" required value={weekStart} onChange={(e) => setWeekStart(e.target.value)} />
          </label>
        </div>
        <label>제목<input aria-label="테마 제목" required maxLength={100} value={title} onChange={(e) => setTitle(e.target.value)} /></label>
        <label>월요일 도입 이야기<textarea aria-label="도입 이야기" required maxLength={2000} value={intro} onChange={(e) => setIntro(e.target.value)} /></label>
        {theme && (theme.outro || theme.introImageUrl || theme.outroImageUrl || theme.introVideoUrl || theme.outroVideoUrl) && (
          // #441: 테마 초안 채택으로 들어온 이야기 그림·종료 이야기. 저장 본문에 넣지 않아 서버가 이전 값을 이어받는다
          <section className="ad-story" aria-label="시작·종료 이야기 미리보기">
            {(['intro', 'outro'] as const).map((k) => (
              <div key={k}>
                <h3>{k === 'intro' ? '시작 이야기 그림' : '종료 이야기'}</h3>
                <ThemeMotionPlayer imageUrl={theme[`${k}ImageUrl`] ?? null} videoUrl={theme[`${k}VideoUrl`] ?? null}
                  motion={theme[`${k}Motion`]} label={k === 'intro' ? '시작 이야기' : '종료 이야기'} />
                {k === 'outro' && <p className="ad-story-text">{theme.outro || '종료 이야기 없음'}</p>}
              </div>
            ))}
            <p className="ad-muted">종료 이야기·그림은 테마 초안에서 만든 값을 보여 줍니다. 이 화면에서 저장해도 그대로 유지됩니다.</p>
          </section>
        )}
        <fieldset>
          <legend>요일별 문제 (게시된 미션, 다섯 생각 유형 하나씩)</legend>
          <QueryFeedback query={missions} />
          {missions.data && !missions.error && !choices.length && (
            <p role="note">게시된 미션이 없어 요일 문제를 고를 수 없습니다. 미션 관리에서 먼저 게시해 주세요.</p>
          )}
          {THEME_DAYS.map((d) => (
            <label key={d}>
              {DAY_LABELS[d]}요일
              <select aria-label={`${DAY_LABELS[d]}요일 미션`} required value={days[d]} onChange={(e) => setDays({ ...days, [d]: e.target.value })}>
                <option value="">미션 선택</option>
                {days[d] && !choices.some(c => c.id === days[d]) && <option value={days[d]}>연결된 미션 · 미션 관리에서 게시 상태 확인</option>}
                {choices.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title}{c.type ? ` · ${thinkingLabels[c.type]}` : ''}{c.grades ? ` · ${c.grades}` : ''}
                  </option>
                ))}
              </select>
              {days[d] && <Link to={'/admin/missions?missionId=' + encodeURIComponent(days[d])}>{DAY_LABELS[d]}요일 미션 편집</Link>}
            </label>
          ))}
          {duplicateType && <p role="alert">같은 생각 유형이 두 번 들어 있습니다. 게시 검사에서 막힙니다.</p>}
        </fieldset>
        <div className="ws-actions">
          <button className="cj-primary" disabled={save.isPending || theme?.status === 'REVIEW_REQUIRED'}>테마 저장</button>
          {theme && theme.status === 'DRAFT' && (
            <button type="button" disabled={action.isPending} onClick={() => run('review-request', '검토를 요청했습니다.')}>검토 요청</button>
          )}
          {theme && theme.status === 'REVIEW_REQUIRED' && (
            <button type="button" disabled={action.isPending} onClick={() => run('publish', '게시했습니다.')}>게시</button>
          )}
          {theme && theme.status === 'PUBLISHED' && (
            <button className="ad-danger" type="button" disabled={action.isPending} onClick={() => run('unpublish', '게시를 중단했습니다.')}>게시 중단</button>
          )}
        </div>
        {problems.length > 0 && (
          <div className="ad-note" role="alert">
            <p>게시 검사를 통과하지 못했습니다.</p>
            <ul>{problems.map((p, i) => <li key={i}>{p}</li>)}</ul>
          </div>
        )}
        <ErrorNotice error={save.error ?? (problems.length ? null : action.error)} />
        <p role="status">{message}</p>
      </form>
    </Panel>
  )
}

/** 꾸미기 아이템 관리 (FN-ADM-23, CONTENT). 새 아이템만 등록하고 삭제 대신 판매 중단한다. */
export function LookItemManager() {
  const list = useAdminQuery(['look-items'], (s) => api.items(s))
  const [editing, setEditing] = useState<AdminLookItem | 'new' | null>(null)
  const rows = list.error ? [] : (list.data?.items ?? [])
  return (
    <div className="ad-two">
      <Panel title="꾸미기 아이템" action={<button onClick={() => setEditing('new')}>새 아이템</button>}>
        <p>테마·캐릭터 해금값은 코드 상수(테마 100·캐릭터 150)이며 여기서 바꾸지 않습니다.</p>
        <QueryFeedback query={list} />
        <div className="ad-table-wrap">
          <table className="ad-table">
            <thead><tr><th>이름</th><th>칸</th><th>필요 포인트</th><th>상태</th><th>관리</th></tr></thead>
            <tbody>
              {rows.map((i) => (
                <tr key={i.itemId}>
                  <td>{i.name}<small>{i.code}</small></td>
                  <td>{SLOT_LABELS[i.slot]}</td>
                  <td>{i.pricePoints}</td>
                  <td><Badge tone={i.status === 'ON_SALE' ? 'success' : 'danger'}>{i.status === 'ON_SALE' ? '판매 중' : '판매 중단'}</Badge></td>
                  <td><button onClick={() => setEditing(i)} aria-label={`${i.name} 아이템 수정`}>수정</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {list.data && !list.error && !rows.length && <Empty>등록한 아이템이 없습니다.</Empty>}
      </Panel>
      {editing && (
        <ItemEditor key={editing === 'new' ? 'new' : editing.itemId} item={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />
      )}
    </div>
  )
}

function ItemEditor({ item, onClose }: { item?: AdminLookItem; onClose: () => void }) {
  const [code, setCode] = useState(item?.code ?? ''), [slot, setSlot] = useState<ItemSlot>(item?.slot ?? 'HAT')
  const [name, setName] = useState(item?.name ?? ''), [price, setPrice] = useState(String(item?.pricePoints ?? 50))
  const [assetKey, setAssetKey] = useState(item?.assetKey ?? ''), [message, setMessage] = useState('')
  const save = useAdminMutation(() =>
    item
      ? api.updateItem(item.itemId, { name: name.trim(), pricePoints: Number(price), assetKey: assetKey.trim() })
      : api.createItem({ code: code.trim(), slot, name: name.trim(), pricePoints: Number(price), assetKey: assetKey.trim() }),
  )
  const toggle = useAdminMutation(() => api.updateItem(item!.itemId, { status: item!.status === 'ON_SALE' ? 'STOPPED' : 'ON_SALE' }))
  const validPrice = /^\d+$/.test(price) && Number(price) >= 1 && Number(price) <= 10000
  return (
    <Panel title={item ? '아이템 수정' : '새 아이템 등록'} action={<button onClick={onClose}>닫기</button>}>
      <form className="ws-form" onSubmit={(e) => {
        e.preventDefault()
        if (!validPrice) return
        void save.mutateAsync(undefined).then(() => { setMessage('아이템을 저장했습니다.'); if (!item) onClose() }).catch(() => {})
      }}>
        <label>코드<input aria-label="아이템 코드" required pattern="[A-Z0-9_]{3,40}" disabled={!!item} value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} /></label>
        <label>칸
          <select aria-label="아이템 칸" disabled={!!item} value={slot} onChange={(e) => setSlot(e.target.value as ItemSlot)}>
            {ALL_ITEM_SLOTS.map((s) => <option key={s} value={s}>{SLOT_LABELS[s]}</option>)}
          </select>
        </label>
        <label>이름<input aria-label="아이템 이름" required maxLength={40} value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label>필요 포인트<input aria-label="필요 포인트" inputMode="numeric" required value={price} onChange={(e) => setPrice(e.target.value)} /></label>
        {!validPrice && <p role="alert">필요 포인트는 1~10000 사이 정수로 적어 주세요.</p>}
        <label>그림 키<input aria-label="그림 키" required maxLength={200} value={assetKey} onChange={(e) => setAssetKey(e.target.value)} /></label>
        <div className="ws-actions">
          <button className="cj-primary" disabled={save.isPending || !validPrice}>저장</button>
          {item && (
            <button className={item.status === 'ON_SALE' ? 'ad-danger' : undefined} type="button" disabled={toggle.isPending} onClick={() => void toggle.mutateAsync(undefined).then(onClose).catch(() => {})}>
              {item.status === 'ON_SALE' ? '판매 중단' : '판매 다시 시작'}
            </button>
          )}
        </div>
        <p>판매를 중단해도 이미 해금한 학생은 계속 쓸 수 있습니다. 아이템은 삭제하지 않습니다.</p>
        <ErrorNotice error={save.error ?? toggle.error} />
        <p role="status">{message}</p>
      </form>
    </Panel>
  )
}
