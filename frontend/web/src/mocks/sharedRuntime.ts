// LAN HTTP에서도 동작하는 시연 전용 fetch 어댑터. 기존 MSW 핸들러를 그대로 실행한다.
// 서비스 워커/카메라 권한 없이 태블릿의 기본 카메라로 연 주소를 사용할 수 있다.
export async function startSharedDemo() {
  if (!crypto.randomUUID) {
    Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: () => {
      const bytes = crypto.getRandomValues(new Uint8Array(16))
      bytes[6] = (bytes[6] & 15) | 64
      bytes[8] = (bytes[8] & 63) | 128
      const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('')
      return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
    } })
  }
  // 이전 일반 MSW 실행에서 남은 worker가 중복으로 응답하지 않게 한다.
  if ('serviceWorker' in navigator) {
    const registration = await navigator.serviceWorker.getRegistration()
    if (registration?.active?.scriptURL === new URL('/mockServiceWorker.js', location.origin).href) {
      await registration.unregister()
      if (navigator.serviceWorker.controller) { location.reload(); await new Promise(() => {}) }
    }
  }
  const { getResponse } = await import('msw')
  const { mockHandlers, installMockEvents } = await import('./browser.ts')
  const original = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const request = input instanceof Request ? new Request(input, init) : new Request(new URL(String(input), location.href), init)
    const url = new URL(request.url)
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/v1/')) return original(input, init)
    if (request.signal.aborted) throw new DOMException('요청을 취소했습니다.', 'AbortError')
    const response = await getResponse(mockHandlers, request, { baseUrl: location.origin })
    return response ?? Response.json({ status: 501, code: 'MOCK_NOT_IMPLEMENTED', title: '아직 준비되지 않은 시연 요청입니다.' }, { status: 501 })
  }
  installMockEvents()
}
