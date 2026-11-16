import { useEffect, useState } from 'react'

const QUERY = '(prefers-reduced-motion: reduce)'
const matches = () => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(QUERY).matches

/** 기기 '동작 줄이기' 설정. 설정이 바뀌면 다시 그린다(움직임 재생기·학생 이야기 화면, #440) */
export function useReducedMotion() {
  const [reduce, setReduce] = useState(matches)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const media = window.matchMedia(QUERY)
    const changed = () => setReduce(media.matches)
    changed()
    media.addEventListener?.('change', changed)
    return () => media.removeEventListener?.('change', changed)
  }, [])
  return reduce
}
