import { useState } from 'react'
import { Lock } from 'lucide-react'
import { useSaveLook, useStudentLook } from '../../../data/studentLook/queries.ts'
import { useLookItems, useMyPoints, useUnlock } from '../../../data/retention/queries.ts'
import { ApiError } from '../../../data/apiClient.ts'
import type { Child } from '../../../domain/classroom.ts'
import { COMPANIONS, THEMES } from '../../../domain/studentLook.ts'
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

const unlockMessage = (e: unknown) => {
  const code = e instanceof ApiError ? e.problem.code : ''
  if (code === 'INSUFFICIENT_POINTS') return '포인트가 조금 모자라요. 미션을 끝내면 포인트가 쌓여요.'
  if (code === 'LOOK_ITEM_NOT_ON_SALE') return '지금은 해금할 수 없는 꾸미기예요.'
  return null
}

/**
 * 꾸미기: 생각 지도(첫 화면)에서 여는 창 (API 명세 2.10·3.12, P22).
 * 호수·뭉치는 처음부터 열려 있고, 나머지는 포인트로 한 번 해금하면 계속 쓸 수 있다(되돌리기·환급 없음).
 * 해금 목록을 받지 못하면 잠금 표시 없이 지금처럼 고르게 두고, 잠긴 값은 서버가 409로 막는다.
 */
export function Customize({ child, onDone }: { child: Child; onDone: () => void }) {
  const { t, companion } = useLook()
  const save = useSaveLook(child.id)
  const look = useStudentLook(child.id).data
  const items = useLookItems(child.id)
  const points = useMyPoints(child.id)
  const unlock = useUnlock(child.id)
  const [unlockKey, setUnlockKey] = useState<{ itemKey: string; key: string } | null>(null)
  const catalog = items.error ? undefined : items.data
  const equipped: Equipped = look?.equipped ?? NO_EQUIPPED
  const choose = (next: { theme?: ThemeId; companion?: CompanionId; equipped?: Equipped }) => {
    unlock.reset() // 고르는 순간에는 저장 상태만 보이게 한다.
    save.mutate({
      theme: next.theme ?? t.id,
      companion: next.companion ?? companion,
      ...(next.equipped || look?.equipped ? { equipped: next.equipped ?? equipped } : {}),
    })
  }
  const locked = (itemKey: string) => !!catalog && !isLookUnlocked(catalog, itemKey)
  const price = (itemKey: string) => catalog?.find((i) => i.itemKey === itemKey)?.pricePoints ?? 0
  /** 같은 항목을 다시 누르면 같은 키로 보내 두 번 차감되지 않게 한다. */
  function askUnlock(itemKey: string) {
    const key = unlockKey?.itemKey === itemKey ? unlockKey.key : crypto.randomUUID()
    setUnlockKey({ itemKey, key })
    unlock.mutate({ itemKey, key }, { onSuccess: () => setUnlockKey(null) })
  }
  const slotItems = (slot: ItemSlot): LookItem[] => (catalog ?? []).filter((i) => i.slot === slot)
  const hasItems = ITEM_SLOTS.some((s) => slotItems(s).length > 0)

  const lockBadge = (itemKey: string) =>
    locked(itemKey) ? (
      <span className="st-lock">
        <Lock aria-hidden="true" size={14} />
        {price(itemKey)}포인트
      </span>
    ) : null
  const unlockButton = (itemKey: string, name: string) =>
    locked(itemKey) ? (
      <button
        type="button"
        className="st-button st-unlock"
        disabled={unlock.isPending}
        onClick={() => askUnlock(itemKey)}
      >
        {name} 해금하기
      </button>
    ) : null

  return (
    <div className="st-custom">
      <p className="st-meta">
        어디서 생각할지, 누구랑 같이 갈지 골라요. 열려 있는 것은 누르면 바로 바뀌어요.
      </p>
      <p className="st-points" role="status">
        {points.data
          ? `내 포인트 ${points.data.balance}`
          : points.isPending
            ? '포인트를 확인하고 있어요.'
            : '포인트를 확인하지 못했어요.'}
      </p>
      <section aria-labelledby="pick-theme">
        <h3 id="pick-theme">어디서 생각할까?</h3>
        <div className="st-pick-grid">
          {Object.values(THEMES).map((th) => (
            <div key={th.id} className="st-pick-cell">
              <button
                type="button"
                className="st-pick"
                aria-pressed={th.id === t.id}
                aria-disabled={locked(themeKey(th.id)) || undefined}
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
                aria-disabled={locked(companionKey(c.id)) || undefined}
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
              <fieldset key={slot} className="st-slot">
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
      <ErrorNotice error={save.error} />
      <p className="st-meta">해금한 꾸미기는 계속 쓸 수 있어요. 한 번 쓴 포인트는 돌려받을 수 없어요.</p>
      <div className="cj-modal-actions">
        <button type="button" className="cj-primary" onClick={onDone}>
          다 골랐어요
        </button>
      </div>
    </div>
  )
}
