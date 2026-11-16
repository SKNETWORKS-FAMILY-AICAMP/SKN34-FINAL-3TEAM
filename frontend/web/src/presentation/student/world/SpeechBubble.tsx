import type { HTMLAttributes, ReactNode } from 'react'
import './bubble.css'

/**
 * 학생 화면 공통 말풍선(#648 38행, 사용자 결정 2026-11-16 "말풍선 부품 하나로").
 * 모양(바탕·테두리·둥글기·그림자·꼬리)은 여기 하나로 두고, 자리·글꼴·안쪽 배치는 쓰는 화면이 정한다.
 * 기준 모양은 홈 말풍선(연노랑 #fffbea, 테두리 2px, 둥글기 22px, 아래 그림자).
 * 꼬리: down = 아래 가운데(캐릭터 머리 위에 뜰 때), left = 왼쪽 아래(캐릭터 얼굴이 왼쪽에 있을 때).
 * 쓰는 쪽이 position(relative·absolute)을 정해야 꼬리가 제자리에 붙는다.
 */
export function SpeechBubble({ tail = 'down', className, children, ...rest }: {
  tail?: 'down' | 'left'
  className?: string
  children: ReactNode
} & Omit<HTMLAttributes<HTMLDivElement>, 'className' | 'children'>) {
  return (
    <div className={`st-bubble st-bubble-${tail}${className ? ` ${className}` : ''}`} {...rest}>
      {children}
    </div>
  )
}
