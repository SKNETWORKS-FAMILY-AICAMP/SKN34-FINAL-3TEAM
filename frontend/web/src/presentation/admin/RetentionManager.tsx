import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { adminApi } from '../../data/admin/api.ts'
import { adminRetentionApi as api } from '../../data/admin/retentionApi.ts'
import { ApiError } from '../../data/apiClient.ts'
import { useAdminMutation, useAdminQuery } from '../../data/admin/queries.ts'
import { thinkingLabels } from '../../domain/classroom.ts'
import { ALL_ITEM_SLOTS, DAY_LABELS, SLOT_LABELS, THEME_DAYS } from '../../domain/retention.ts'
import type { ItemSlot, ThemeDay } from '../../domain/retention.ts'
import {
  THEME_GRADE_LABELS,
  THEME_STATUS_LABELS,
  publishProblems,
} from '../../domain/admin/retention.ts'
import type { AdminLookItem, AdminWeeklyTheme, ThemeGrade } from '../../domain/admin/retention.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ThemeMotionPlayer } from '../common/ThemeMotionPlayer.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { Badge, Empty, Panel, TableScroll } from './AdminUi.tsx'
import { WeeklyThemePlanner } from './WeeklyThemePlanner.tsx'
import { busyProps } from './busyButton.ts'

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
  const [params, setParams] = useSearchParams()
  const themeId = params.get('themeId') ?? ''
  const linked = useAdminQuery(['weekly-theme', themeId], signal => api.theme(themeId, signal), !!themeId && themeId !== 'new')
  const selectId = (id: string | null, theme?: AdminWeeklyTheme) => {
    const next = new URLSearchParams(params)
    if (id) next.set('themeId',id); else { next.delete('themeId'); next.delete('day') }
    if (theme) { next.set('grade',theme.grade); next.set('weekStart',theme.weekStart) }
    setParams(next)
  }
  if (!themeId) return <WeeklyThemePlanner onOpen={id=>selectId(id)} onCreate={()=>selectId('new')}/>
  if (themeId==='new') return <ThemeEditor onSaved={t=>selectId(t.themeId,t)} onClose={()=>selectId(null)}/>
  if (!linked.data || linked.error) return <><button onClick={()=>selectId(null)}>편성 보드로</button><QueryFeedback query={linked}/></>
  const theme = linked.data
  const close = () => selectId(null,theme)
  if (theme.weekLocked && theme.status !== 'PUBLISHED') return <Panel title="다른 테마가 게시 중인 주차" action={<button onClick={close}>편성 보드로</button>}>
    <div className="ad-plan-readonly"><p>{THEME_GRADE_LABELS[theme.grade]} · 적용 주 {theme.weekStart} · {THEME_STATUS_LABELS[theme.status]} · 읽기 전용</p>
      {theme.generationWeek && theme.generationWeek!==theme.weekStart && <p>생성 기준 주 {theme.generationWeek}</p>}
      <h3>{theme.title}</h3><p>{theme.intro}</p><ThemeMotionPlayer label="시작 이야기" imageUrl={theme.introImageUrl??null} videoUrl={theme.introVideoUrl??null} motion={theme.introMotion}/>
      {theme.days.map(day=><article key={day.day}><h3>{DAY_LABELS[day.day]}요일 · {day.title??'요일 미션'}</h3>
        <ThemeMotionPlayer label={DAY_LABELS[day.day]+'요일 장면'} imageUrl={day.sceneImageUrl??null} videoUrl={day.videoUrl??null} motion={day.sceneMotion}/>{day.clue&&<p>{day.clue}</p>}</article>)}
      <article><h3>종료 이야기</h3><p>{theme.outro}</p><ThemeMotionPlayer label="종료 이야기" imageUrl={theme.outroImageUrl??null} videoUrl={theme.outroVideoUrl??null} motion={theme.outroMotion}/></article>
    </div></Panel>
  const activeDay = THEME_DAYS.find(d=>d===params.get('day'))
  return <ThemeEditor key={theme.themeId} theme={theme} activeDay={activeDay} onSaved={t=>selectId(t.themeId,t)} onClose={close}/>
}

function ThemeEditor({
  theme,
  activeDay,
  onSaved,
  onClose,
}: {
  theme?: AdminWeeklyTheme
  activeDay?: ThemeDay
  onSaved: (t: AdminWeeklyTheme) => void
  onClose: () => void
}) {
  const [grade, setGrade] = useState<ThemeGrade>(theme?.grade ?? 'G3')
  const [weekStart, setWeekStart] = useState(theme?.weekStart ?? nextMonday())
  const live = theme?.status === 'PUBLISHED'
  const hasPublication = live || theme?.publishedVersion != null
  const fixedSchedule = theme?.generationWeek != null || live ? theme : undefined
  const [formVersion, setFormVersion] = useState(theme?.version)
  const [title, setTitle] = useState(theme?.title ?? ''), [intro, setIntro] = useState(theme?.intro ?? '')
  const [days, setDays] = useState<Record<ThemeDay, string>>(
    () => Object.fromEntries(THEME_DAYS.map((d) => [d, theme?.days.find((x) => x.day === d)?.missionId ?? ''])) as Record<ThemeDay, string>,
  )
  const [message, setMessage] = useState('')
  const [decision, setDecision] = useState<{action:'publish' | 'unpublish'; version:number} | null>(null)
  const returnFocus = useRef<HTMLSelectElement>(null)
  useEffect(()=>{ if (activeDay) returnFocus.current?.focus() },[activeDay])
  const missions = useAdminQuery(['missions', 'theme-picker'], (s) => adminApi.missions({ status: 'PUBLISHED' }, s))
  const choices = (missions.error ? [] : (missions.data?.items ?? [])).map((m) => {
    const v = m.versions.find((x) => x.version === (m.publishedVersion ?? m.currentVersion)) ?? m.versions.at(-1)
    return { id: m.missionId, title: v?.title ?? m.missionId, type: v?.thinkingType, grades: v ? `초${v.gradeMin}~${v.gradeMax}` : '' }
  })
  const input = () => ({ grade: fixedSchedule?.grade ?? grade, weekStart: fixedSchedule?.weekStart ?? weekStart,
    title: title.trim(), intro: intro.trim(), days: THEME_DAYS.map((day) => ({ day, missionId: days[day] })) })
  const save = useAdminMutation(() => (theme ? api.saveTheme(theme.themeId, input(), hasPublication ? formVersion : undefined) : api.createTheme(input())))
  const review = useAdminMutation(() => api.themeAction(theme!.themeId, 'review-request', hasPublication ? { expectedVersion: formVersion } : {}))
  const publication = useAdminMutation((choice: NonNullable<typeof decision>) => api.themeAction(theme!.themeId, choice.action,
    choice.action === 'publish' ? { expectedVersion: choice.version, expectedPlannedDraftId: null } : { expectedPublishedVersion: choice.version }))
  const busy = save.isPending || review.isPending || publication.isPending
  const changed = theme && (title.trim() !== theme.title || intro.trim() !== theme.intro ||
    THEME_DAYS.some(day => days[day] !== (theme.days.find(d => d.day === day)?.missionId ?? '')))
  const staleForm = hasPublication && formVersion !== theme?.version
  const newer = live && theme.version != null && theme.publishedVersion != null && theme.version > theme.publishedVersion
  const problems = publication.error instanceof ApiError ? publishProblems(publication.error.problem) : []
  const types = THEME_DAYS.map((d) => choices.find((c) => c.id === days[d])?.type).filter(Boolean)
  const duplicateType = new Set(types).size !== types.length
  const requestReview = () => void review.mutateAsync(undefined).then(t => {
    onSaved(t)
    if (live) setMessage('수정본 검토를 요청했습니다.')
    else onClose()
  }).catch(()=>{})
  const decide = (action: 'publish' | 'unpublish', version: number) => {
    publication.reset()
    setDecision({ action, version })
  }
  const confirm = () => {
    if (!decision || busy) return
    void publication.mutateAsync(decision).then(t => {
      onSaved(t)
      setMessage(decision.action === 'publish' ? '수정본을 재게시했습니다.' : '테마 제공을 중단했습니다.')
      setDecision(null)
    }).catch(()=>{})
  }
  return (
    <Panel title={live ? '게시 테마 관리' : theme ? '테마 수정·검토' : '새 테마 작성'} action={<button onClick={onClose}>{live ? '편성 보드로' : '닫기'}</button>}>
      {live && <p><strong>학생 게시본{theme.publishedVersion != null && ' v'+theme.publishedVersion}</strong>
        {theme.version != null && ' · 작업본 v'+theme.version}
        {newer && (theme.reviewRequested ? ' · 재게시 검토 대기' : ' · 수정본 저장됨')}</p>}
      {theme?.status === 'UNPUBLISHED' && <p>제공 중단 상태입니다. 검토를 요청한 뒤 편성 보드에서 게시하면 다시 제공됩니다.</p>}
      <form
        className="ws-form"
        onSubmit={(e) => {
          e.preventDefault()
          if (busy || staleForm) return
          void save.mutateAsync(undefined).then((t) => { setFormVersion(t.version); onSaved(t); setMessage('테마를 저장했습니다.') }).catch(() => {})
        }}
      >
        {fixedSchedule ? <fieldset>
          <legend>{fixedSchedule.generationWeek ? '채택 시 확정된 편성' : '게시 중인 편성'}</legend>
          <p>{THEME_GRADE_LABELS[fixedSchedule.grade]} · 적용 주 {fixedSchedule.weekStart}</p>
          {fixedSchedule.generationWeek && fixedSchedule.generationWeek !== fixedSchedule.weekStart && <p>생성 기준 주 {fixedSchedule.generationWeek}</p>}
        </fieldset> : <div className="ad-two">
          <label>학년
            <select aria-label="학년" value={grade} onChange={(e) => setGrade(e.target.value as ThemeGrade)}>
              {Object.entries(THEME_GRADE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label>주 시작(월요일)
            <input type="date" aria-label="주 시작일" required value={weekStart} onChange={(e) => setWeekStart(e.target.value)} />
          </label>
        </div>}
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
              <select ref={activeDay===d?returnFocus:undefined} aria-label={`${DAY_LABELS[d]}요일 미션`} required value={days[d]} onChange={(e) => setDays({ ...days, [d]: e.target.value })}>
                <option value="">미션 선택</option>
                {days[d] && !choices.some(c => c.id === days[d]) && <option value={days[d]}>연결된 미션 · 미션 관리에서 게시 상태 확인</option>}
                {choices.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title}{c.type ? ` · ${thinkingLabels[c.type]}` : ''}{c.grades ? ` · ${c.grades}` : ''}
                  </option>
                ))}
              </select>
              {days[d] && <Link to={'/admin/missions?' + new URLSearchParams({missionId:days[d],...(theme?{themeId:theme.themeId,themeDay:d}:{})})}>{DAY_LABELS[d]}요일 미션 편집</Link>}
            </label>
          ))}
          {duplicateType && <p role="alert">같은 생각 유형이 두 번 들어 있습니다. 게시 검사에서 막힙니다.</p>}
        </fieldset>
        {live && <details className="ad-story"><summary>작업본의 요일별 장면</summary>
          {theme.days.map(day => <article key={day.day}><h3>{DAY_LABELS[day.day]}요일 · {day.title ?? '요일 미션'}</h3>
            <ThemeMotionPlayer label={DAY_LABELS[day.day]+'요일 장면'} imageUrl={day.sceneImageUrl ?? null} videoUrl={day.videoUrl ?? null} motion={day.sceneMotion}/>
            {day.clue && <p>{day.clue}</p>}</article>)}
        </details>}
        {staleForm && <p role="alert">다른 관리자가 수정본을 저장했습니다. 편성 보드에서 테마를 다시 열어 최신 내용을 확인해 주세요.</p>}
        <div className="ws-actions">
          <button className="cj-primary" {...busyProps(busy, staleForm || theme?.status === 'REVIEW_REQUIRED' || (live && !changed))}>테마 저장</button>
          {theme && (theme.status==='DRAFT'||theme.status==='UNPUBLISHED') && <button type="button" {...busyProps(busy, hasPublication && (staleForm || changed))} onClick={requestReview}>검토 요청</button>}
          {theme?.status==='REVIEW_REQUIRED' && <button type="button" onClick={onClose}>편성 보드에서 게시</button>}
          {newer && !theme.reviewRequested && <button type="button" {...busyProps(busy, staleForm || changed)} onClick={requestReview}>수정본 검토 요청</button>}
          {newer && theme.reviewRequested && <button type="button" {...busyProps(busy, staleForm || changed)} onClick={() => decide('publish', theme.version!)}>수정본 재게시</button>}
          {live && theme.publishedVersion != null && <button type="button" className="ad-danger" {...busyProps(busy)} onClick={() => decide('unpublish', theme.publishedVersion!)}>제공 중단</button>}
        </div>
        <ErrorNotice error={save.error ?? review.error} />
        <p role="status">{message}</p>
      </form>
      {decision && theme && <Modal title={decision.action === 'publish' ? '수정본을 재게시할까요?' : '학생에게 테마 제공을 중단할까요?'}
        onClose={() => { if (!busy) setDecision(null) }}>
        <p>{THEME_GRADE_LABELS[theme.grade]} · {theme.weekStart} · v{decision.version}</p>
        <p>{decision.action === 'publish' ? '검토한 수정본을 학생에게 공개합니다.' : '이 테마의 신규 제공을 중단합니다. 이미 시작한 학습은 이어갈 수 있습니다.'}</p>
        {problems.length > 0 ? <ul role="alert">{problems.map(p => <li key={p}>{p}</li>)}</ul> : <ErrorNotice error={publication.error}/>}
        <div className="ws-actions"><button {...busyProps(busy)} onClick={() => setDecision(null)}>취소</button>
          <button className={decision.action === 'publish' ? 'cj-primary' : 'ad-danger'} {...busyProps(busy, publication.isError)} onClick={confirm}>
            {decision.action === 'publish' ? '재게시 확정' : '제공 중단 확정'}</button></div>
      </Modal>}
    </Panel>
  )
}

/** 꾸미기 아이템 관리 (FN-ADM-23, CONTENT). 새 아이템만 등록하고 삭제 대신 판매 중단한다. */
export function LookItemManager() {
  const [slot, setSlot] = useState('')
  const [page, setPage] = useState(0)
  const list = useAdminQuery(['look-items', slot, page], (s) => api.items(s, slot, page))
  const [editing, setEditing] = useState<AdminLookItem | 'new' | null>(null)
  const rows = list.error ? [] : (list.data?.items ?? [])
  return (
    <div className="ad-two">
      <Panel title="꾸미기 아이템" action={<button onClick={() => setEditing('new')}>새 아이템</button>}>
        <p>테마·캐릭터 해금값은 코드 상수(테마 100·캐릭터 150)이며 여기서 바꾸지 않습니다.</p>
        <div className="ad-filters"><label>칸 필터
          <select aria-label="아이템 칸 필터" value={slot} onChange={(e) => { setSlot(e.target.value); setPage(0) }}>
            <option value="">전체</option>
            {ALL_ITEM_SLOTS.map((s) => <option key={s} value={s}>{SLOT_LABELS[s]}</option>)}
          </select>
        </label></div>
        <QueryFeedback query={list} />
        <TableScroll label="꾸미기 아이템 표">
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
        </TableScroll>
        {list.data && !list.error && !rows.length && <Empty>등록한 아이템이 없습니다.</Empty>}
        {list.data && !list.error && list.data.totalElements > list.data.size && <div className="ws-actions" aria-label="아이템 목록 페이지">
          <button disabled={page === 0} onClick={() => setPage(page - 1)}>이전 아이템</button>
          <span>{page + 1}페이지</span>
          <button disabled={(page + 1) * list.data.size >= list.data.totalElements} onClick={() => setPage(page + 1)}>다음 아이템</button>
        </div>}
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
        <label>그림 키<input aria-label="그림 키" required maxLength={200} value={assetKey} aria-describedby="item-asset-help" onChange={(e) => setAssetKey(e.target.value)} /></label>
        <small id="item-asset-help">모자·옷·소품은 web <code>public/student-assets/</code> 안 파일 경로(예 looks/hat-acorn.svg, 영문 소문자·숫자·-·_, svg·png·webp). 벽지·가구·바닥·방 소품은 <code>roomAssets.ts</code>의 내 방 그림 표에 등록된 키(room/…)를 사용합니다. 파일이 없으면 기본 모습으로 보입니다.</small>
        {slot === 'DECOR' && <p>방 소품은 여러 개 구매해서 방에 배치하는 항목이며, 캐릭터가 착용하는 소품과 다릅니다.</p>}
        {slot === 'FLOOR' && <p>바닥은 한 번 해금한 뒤 방에 적용하는 항목입니다.</p>}
        <div className="ws-actions">
          <button className="cj-primary" {...busyProps(save.isPending, !validPrice)}>저장</button>
          {item && (
            <button className={item.status === 'ON_SALE' ? 'ad-danger' : undefined} type="button" {...busyProps(toggle.isPending)} onClick={() => void toggle.mutateAsync(undefined).then(onClose).catch(() => {})}>
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
