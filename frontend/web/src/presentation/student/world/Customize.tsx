import { useEffect, useRef, useState } from 'react'
import { Lock } from 'lucide-react'
import { useSaveLook, useStudentLook } from '../../../data/studentLook/queries.ts'
import { useLookItems, useMyPoints, useUnlock } from '../../../data/retention/queries.ts'
import { ApiError } from '../../../data/apiClient.ts'
import type { Child } from '../../../domain/classroom.ts'
import { companionLabel, COMPANIONS, THEMES } from '../../../domain/studentLook.ts'
import type { CompanionId, ThemeId } from '../../../domain/studentLook.ts'
import {
  companionKey,
  isLookUnlocked,
  ITEM_SLOTS,
  NO_EQUIPPED,
  SLOT_LABELS,
  themeKey,
} from '../../../domain/retention.ts'
import type { Equipped, ItemSlot, LookItem } from '../../../domain/retention.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { Companion } from './Companion.tsx'
import { ThemeSwatch } from './ThemeArt.tsx'
import { useLook } from './lookContext.ts'
import './retention.css'

const unlockMessage = (e: unknown) => {
  const code = e instanceof ApiError ? e.problem.code : ''
  if (code === 'INSUFFICIENT_POINTS') return '포인트가 조금 모자라요. 미션을 끝내면 포인트가 쌓여요.'
  if (code === 'LOOK_ITEM_NOT_ON_SALE') return '지금은 해금할 수 없는 꾸미기예요.'
  if (code === 'LOOK_LOCKED') return '아직 해금하지 않은 꾸미기예요. 목록을 다시 확인해 주세요.'
  if (code === 'LOOK_ITEM_NOT_FOUND') return '이 꾸미기를 찾지 못했어요. 목록을 다시 확인해 주세요.'
  return null
}

/**
 * 꾸미기: 생각 지도(첫 화면)에서 여는 창 (API 명세 2.10·3.12, P22).
 * 호수·뭉치는 처음부터 열려 있고, 나머지는 포인트로 한 번 해금하면 계속 쓸 수 있다(되돌리기·환급 없음).
 * #389의 해금 확정 응답과 소유 목록을 기준으로 선택·착용한다.
 */
export function Customize({ child, onDone }: { child: Child; onDone: () => void }) {
  return <StudentCustomize key={child.id} child={child} onDone={onDone} />
}
function StudentCustomize({ child, onDone }: { child: Child; onDone: () => void }) {
  const { t, companion } = useLook()
  const save = useSaveLook(child.id)
  const settings = useStudentLook(child.id)
  const look = settings.data
  const items = useLookItems(child.id)
  const points = useMyPoints(child.id)
  const unlock = useUnlock(child.id)
  const [confirming, setConfirming] = useState<string | null>(null)
  const unlockKeys = useRef(new Map<string, string>())
  const confirmation = useRef<HTMLElement>(null)
  useEffect(() => { if (confirming) confirmation.current?.focus() }, [confirming])
  const catalog = items.error ? undefined : items.data
  const equipped: Equipped = look?.equipped ?? NO_EQUIPPED
  const balance = !points.error ? points.data?.balance : undefined
  const busy = save.isPending || unlock.isPending
  const choosingBlocked = busy || settings.isPending || settings.isError || confirming !== null
  const pendingItem = catalog?.find(i => i.itemKey === confirming)
  const affordable = pendingItem && balance !== undefined && balance >= pendingItem.pricePoints
  const choose = (next: { theme?: ThemeId; companion?: CompanionId; equipped?: Equipped }) => {
    if (choosingBlocked) return
    unlock.reset() // 고르는 순간에는 저장 상태만 보이게 한다.
    save.mutate({
      theme: next.theme ?? t.id,
      companion: next.companion ?? companion,
      ...(next.equipped ? { equipped: next.equipped } : {}),
    })
  }
  const locked = (itemKey: string) => !isLookUnlocked(catalog, itemKey) &&
    !(!catalog && look && (itemKey === themeKey(look.theme) || itemKey === companionKey(look.companion)))
  const price = (itemKey: string) => catalog?.find((i) => i.itemKey === itemKey)?.pricePoints ?? 0
  /** 응답 유실 뒤에도 같은 항목은 같은 키로 재전송한다. */
  function confirmUnlock() {
    if (!pendingItem || !affordable || busy || !pendingItem.onSale || pendingItem.unlocked) return
    const itemKey = pendingItem.itemKey
    let key = unlockKeys.current.get(itemKey)
    if (!key) { key = crypto.randomUUID(); unlockKeys.current.set(itemKey, key) }
    unlock.mutate({ itemKey, key }, { onSuccess: () => {
      unlockKeys.current.delete(itemKey)
      setConfirming(null)
    } })
  }
  const slotItems = (slot: ItemSlot): LookItem[] => (catalog ?? []).filter((i) => i.slot === slot)
  const hasItems = ITEM_SLOTS.some((s) => slotItems(s).length > 0)

  const lockBadge = (itemKey: string) =>
    locked(itemKey) ? (
      <span className="st-lock">
        <Lock aria-hidden="true" size={14} />
        {catalog?.some(i => i.itemKey === itemKey) ? `${price(itemKey).toLocaleString('ko-KR')}포인트` : '해금 확인 필요'}
      </span>
    ) : null
  const unlockButton = (itemKey: string, name: string) =>
    locked(itemKey) && catalog?.some(i => i.itemKey === itemKey && i.onSale) ? (
      <button
        type="button"
        className="st-button st-unlock"
        disabled={busy || confirming !== null || balance === undefined}
        onClick={() => { save.reset(); unlock.reset(); setConfirming(itemKey) }}
      >
        {name} 해금하기
      </button>
    ) : null

  return (
    <div className="st-custom" aria-busy={busy}>
      <div className="st-custom-summary">
        <Companion kind={companion} size={88} decorative />
        <div><p className="st-meta">{t.title} · {companionLabel(companion)}</p>
          <p className="st-points" role="status">{balance !== undefined ? `내 포인트 ${balance.toLocaleString('ko-KR')}`
            : points.isPending ? '포인트를 확인하고 있어요.' : '포인트를 확인하지 못했어요.'}</p>
          <p className="st-meta">열린 꾸미기는 누르면 바로 저장돼요.</p>
        </div>
      </div>
      <ErrorNotice error={points.error} retry={() => void points.refetch()} />
      <ErrorNotice error={items.error} retry={() => void items.refetch()} />
      <ErrorNotice error={settings.error} retry={() => void settings.refetch()} />
      {items.isPending && <p role="status">열린 꾸미기를 확인하고 있어요.</p>}
      {items.isError && <p className="st-meta">열린 꾸미기를 확인한 뒤 해금할 수 있어요. 기본 모습과 지금 쓰는 모습은 유지돼요.</p>}
      {confirming && <section ref={confirmation} tabIndex={-1} className="st-unlock-confirm" aria-label="꾸미기 해금 확인">
        <h3>{pendingItem?.name ?? '꾸미기'} 해금할까요?</h3>
        {pendingItem && balance !== undefined && <p>{pendingItem.pricePoints.toLocaleString('ko-KR')}포인트를 써요.
          {affordable ? ` 해금 후 ${Math.max(0, balance - pendingItem.pricePoints).toLocaleString('ko-KR')}포인트가 남아요.`
            : ` ${Math.max(0, pendingItem.pricePoints - balance).toLocaleString('ko-KR')}포인트가 더 필요해요.`}</p>}
        <p className="st-meta">한 번 열면 계속 쓸 수 있어요. 쓴 포인트는 돌려받을 수 없어요.</p>
        <div className="st-custom-actions">
          <button type="button" className="st-button" disabled={busy} onClick={() => { setConfirming(null); unlock.reset() }}>취소</button>
          <button type="button" className="st-button st-primary" disabled={busy || !affordable || !pendingItem?.onSale || pendingItem?.unlocked}
            onClick={confirmUnlock}>{unlock.isPending ? '해금하는 중이에요' : '포인트로 해금하기'}</button>
        </div>
      </section>}
      <section aria-labelledby="pick-theme">
        <h3 id="pick-theme">어디서 생각할까?</h3>
        <div className="st-pick-grid">
          {Object.values(THEMES).map((th) => (
            <div key={th.id} className="st-pick-cell">
              <button
                type="button"
                className="st-pick"
                aria-pressed={th.id === t.id}
                disabled={choosingBlocked || locked(themeKey(th.id))}
                onClick={() => (locked(themeKey(th.id)) ? undefined : choose({ theme: th.id }))}
              >
                <ThemeSwatch t={th} />
                <strong>{th.name}</strong>
                <small>{th.title}</small>
                {lockBadge(themeKey(th.id))}
              </button>
              {unlockButton(themeKey(th.id), th.name)}
            </div>
          ))}
        </div>
      </section>
      <section aria-labelledby="pick-buddy">
        <h3 id="pick-buddy">누구랑 같이 갈까?</h3>
        <div className="st-pick-grid">
          {COMPANIONS.map((c) => (
            <div key={c.id} className="st-pick-cell">
              <button
                type="button"
                className="st-pick st-pick-buddy"
                aria-pressed={c.id === companion}
                disabled={choosingBlocked || locked(companionKey(c.id))}
                onClick={() => (locked(companionKey(c.id)) ? undefined : choose({ companion: c.id }))}
              >
                <Companion kind={c.id} size={72} decorative />
                <strong>{c.label}</strong>
                <small>{c.desc}</small>
                {lockBadge(companionKey(c.id))}
              </button>
              {unlockButton(companionKey(c.id), c.label)}
            </div>
          ))}
        </div>
      </section>
      {hasItems && (
        <section aria-labelledby="pick-items">
          <h3 id="pick-items">캐릭터에게 입혀 볼까?</h3>
          {ITEM_SLOTS.map((slot) =>
            slotItems(slot).length ? (
              <fieldset key={slot} className="st-slot" disabled={choosingBlocked}>
                <legend>{SLOT_LABELS[slot]}</legend>
                <label>
                  <input
                    type="radio"
                    name={`slot-${slot}`}
                    checked={!equipped[slot]}
                    onChange={() => choose({ equipped: { ...equipped, [slot]: null } })}
                  />
                  안 입기
                </label>
                {slotItems(slot).map((item) => (
                  <span key={item.itemKey} className="st-slot-item">
                    <label>
                      <input
                        type="radio"
                        name={`slot-${slot}`}
                        disabled={!item.unlocked}
                        checked={equipped[slot] === item.itemKey}
                        onChange={() => choose({ equipped: { ...equipped, [slot]: item.itemKey } })}
                      />
                      {item.name}
                      {!item.unlocked && ` · ${item.pricePoints}포인트`}
                      {item.unlocked && !item.onSale && ' · 보유 중'}
                    </label>
                    {!item.unlocked && item.onSale && unlockButton(item.itemKey, item.name)}
                  </span>
                ))}
              </fieldset>
            ) : null,
          )}
        </section>
      )}
      <p className="st-meta" role="status">
        {unlock.isPending
          ? '해금하는 중이에요.'
          : unlock.isSuccess
            ? '해금했어요! 이제 골라서 쓸 수 있어요.'
            : save.isPending
              ? '저장하는 중이에요.'
              : save.isSuccess
                ? '골랐어요. 다른 기기에서도 그대로 보여요.'
                : save.isError
                  ? '저장하지 못해서 전에 고른 모습으로 돌아갔어요. 잠시 뒤에 다시 골라 주세요.'
                  : ''}
      </p>
      {unlock.isError && (unlockMessage(unlock.error) ? <p role="alert">{unlockMessage(unlock.error)}</p> : <ErrorNotice error={unlock.error} />)}
      {unlockMessage(save.error) ? <p role="alert">{unlockMessage(save.error)}</p> : <ErrorNotice error={save.error} />}
      <p className="st-meta">해금한 꾸미기는 계속 쓸 수 있어요. 한 번 쓴 포인트는 돌려받을 수 없어요.</p>
      <div className="cj-modal-actions">
        <button type="button" className="cj-primary" disabled={busy} onClick={onDone}>
          다 골랐어요
        </button>
      </div>
    </div>
  )
}
