import { createContext, useContext } from 'react'
import type { CSSProperties } from 'react'
import { THEMES } from '../../../domain/studentLook.ts'
import type { CompanionId, Theme } from '../../../domain/studentLook.ts'

export interface Look {
  t: Theme
  companion: CompanionId
}
export const LookContext = createContext<Look>({ t: THEMES.lake, companion: 'mungchi' })
/** 지금 학생이 고른 테마·캐릭터 (StudentWorld 안에서만 의미가 있다). */
export const useLook = () => useContext(LookContext)

export const themeVars = (t: Theme) =>
  ({
    '--st-bg': t.bg,
    '--st-shade': t.shade,
    '--st-light': t.light,
    '--st-light2': t.light2,
    '--st-top': t.top,
    '--st-side': t.side,
  }) as CSSProperties
