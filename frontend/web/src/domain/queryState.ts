/** api-spec 1.5 조회 상태. HELD는 판정 결과이므로 이 상태에 섞지 않는다. */
export type QueryState = 'OK' | 'NO_RECORD' | 'INSUFFICIENT_SAMPLE' | 'PROCESSING' | 'FAILED'
