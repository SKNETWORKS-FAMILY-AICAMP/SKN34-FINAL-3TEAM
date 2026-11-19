package com.sagomungchi.core.report.client

import com.sagomungchi.core.report.domain.ReportPeriodType
import java.time.LocalDate
import java.util.UUID

/**
 * 판정 정정 영향 조회(#244, FN-SUP-03)에서 그 시도로 만든 완료 판 하나. [ReportClient.correctionImpact]가 report-api
 * `CorrectionImpactItem` 계약(UUID·주기 열거값·날짜·1 이상 회차)을 검사한 뒤에만 만든다(#814 후속).
 */
data class AffectedReport(val reportId: UUID, val periodType: ReportPeriodType, val periodFrom: LocalDate, val revision: Int)
