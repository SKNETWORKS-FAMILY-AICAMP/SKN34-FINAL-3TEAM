const formatter = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', year: 'numeric', month: 'long', day: 'numeric',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})

/** API의 ISO 시각은 브라우저 시간대와 무관하게 한국 시간으로 표시한다. */
export function formatKoreanDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '시각 확인 불가' : formatter.format(parsed)
}
