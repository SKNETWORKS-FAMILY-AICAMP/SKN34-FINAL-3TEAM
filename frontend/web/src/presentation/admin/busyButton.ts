import { useEffect } from 'react'

/**
 * 처리 중인 단추의 속성 (#917). `disabled`로 끄면 초점을 가진 단추에서 초점이 body로 빠지므로
 * 처리 중에는 `aria-disabled`만 두어 초점을 유지하고, 눌림은 `useBusyClickGuard`가 막는다.
 * 입력 부족처럼 처리 중이 아닌 이유(`disabled`)는 그대로 끈다.
 */
export function busyProps(busy: boolean, disabled = false) {
  return { disabled: disabled || undefined, 'aria-disabled': busy && !disabled ? true : undefined }
}

/** `aria-disabled="true"` 단추의 클릭(Enter·Space·폼 Enter 제출 포함)을 React 처리 전에 막는다. 관리자 화면에서만 건다. */
export function useBusyClickGuard() {
  useEffect(() => {
    const block = (event: MouseEvent) => {
      if (!(event.target instanceof Element) || !event.target.closest('button[aria-disabled="true"]')) return
      event.preventDefault()
      event.stopImmediatePropagation()
    }
    document.addEventListener('click', block, true)
    return () => document.removeEventListener('click', block, true)
  }, [])
}
