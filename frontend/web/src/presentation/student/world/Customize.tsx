import { useSaveLook } from '../../../data/studentLook/queries.ts'
import type { Child } from '../../../domain/classroom.ts'
import { COMPANIONS, THEMES } from '../../../domain/studentLook.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { Companion } from './Companion.tsx'
import { ThemeSwatch } from './ThemeArt.tsx'
import { useLook } from './lookContext.ts'

/** 꾸미기: 생각 지도(첫 화면)에서 여는 창. 테마·캐릭터를 고르는 즉시 바뀌고 저장된다 (API 명세 3.12). */
export function Customize({ child, onDone }: { child: Child; onDone: () => void }) {
  const { t, companion } = useLook()
  const save = useSaveLook(child.id)
  return (
    <div className="st-custom">
      <p className="st-meta">어디서 생각할지, 누구랑 같이 갈지 골라요. 누르면 바로 바뀌어요.</p>
      <section aria-labelledby="pick-theme">
        <h3 id="pick-theme">어디서 생각할까?</h3>
        <div className="st-pick-grid">
          {Object.values(THEMES).map((th) => (
            <button
              type="button"
              key={th.id}
              className="st-pick"
              aria-pressed={th.id === t.id}
              onClick={() => save.mutate({ theme: th.id, companion })}
            >
              <ThemeSwatch t={th} />
              <strong>{th.name}</strong>
              <small>{th.title}</small>
            </button>
          ))}
        </div>
      </section>
      <section aria-labelledby="pick-buddy">
        <h3 id="pick-buddy">누구랑 같이 갈까?</h3>
        <div className="st-pick-grid">
          {COMPANIONS.map((c) => (
            <button
              type="button"
              key={c.id}
              className="st-pick st-pick-buddy"
              aria-pressed={c.id === companion}
              onClick={() => save.mutate({ theme: t.id, companion: c.id })}
            >
              <Companion kind={c.id} size={72} decorative />
              <strong>{c.label}</strong>
              <small>{c.desc}</small>
            </button>
          ))}
        </div>
      </section>
      <p className="st-meta" role="status">
        {save.isPending ? '저장하는 중이에요.' : save.isSuccess ? '골랐어요. 다른 기기에서도 그대로 보여요.' : ''}
      </p>
      <ErrorNotice error={save.error} />
      <div className="cj-modal-actions">
        <button type="button" className="cj-primary" onClick={onDone}>
          다 골랐어요
        </button>
      </div>
    </div>
  )
}
