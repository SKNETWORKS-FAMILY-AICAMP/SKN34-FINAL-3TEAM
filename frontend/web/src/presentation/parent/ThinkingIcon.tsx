/** Small two-tone illustrations shared by the chart and thinking activity list. */
export function ThinkingIcon({ type }: { type: string }) {
  return <svg className="pd-thinking-icon" viewBox="0 0 40 40" fill="none" aria-hidden="true" focusable="false" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    {type === 'ANALYZE' && <><circle cx="17" cy="16" r="10" fill="var(--type-soft)" /><path d="m24 24 10 10" strokeWidth="5" /><path d="m12 18 4-5 4 3 3-5" /><path d="M10 7 7 4M5 13H2" stroke="var(--type-bright)" /></>}
    {type === 'EVALUATE' && <><path d="M20 7v26M12 34h16M7 12h26" /><circle cx="20" cy="8" r="3" fill="var(--type-bright)" /><path d="m9 13-5 11h10L9 13Zm22 0-5 11h10l-5-11Z" fill="var(--type-soft)" /><path d="M4 25q5 7 10 0M26 25q5 7 10 0" fill="var(--type-bright)" /></>}
    {type === 'CREATE' && <><path d="M12 19a10 10 0 1 1 16 0c-3 3-3 5-3 7H15c0-2 0-4-3-7Z" fill="var(--type-bright)" /><path d="M15 30h10M17 34h6M20 25v-8m-4-1 4 3 4-3M20 1v2M4 9l3 2M33 11l3-2" /><path d="m32 27 2-3 2 3 3 1-3 1-2 3-2-3-3-1Z" fill="var(--type-soft)" strokeWidth="1.4" /></>}
    {type === 'SOLVE' && <><path d="M7 8h10c-3 7 9 7 6 0h10v10c-7-3-7 9 0 6v9H23c3-7-9-7-6 0H7v-9c7 3 7-9 0-6V8Z" fill="var(--type-soft)" /><path d="m16 21 4 4 7-8" strokeWidth="3" /><circle cx="33" cy="7" r="4" fill="var(--type-bright)" stroke="white" /></>}
    {type === 'REFLECT' && <><path d="M8 14a14 14 0 1 1-1 14M8 6v9H2" strokeWidth="3" /><path d="M14 17q6-5 12 0v11q-6-5-12 0V17Z" fill="var(--type-soft)" /><path d="M20 16v9M30 6l2-4 2 4 4 2-4 2-2 4-2-4-4-2Z" fill="var(--type-bright)" strokeWidth="1.4" /></>}
  </svg>
}
