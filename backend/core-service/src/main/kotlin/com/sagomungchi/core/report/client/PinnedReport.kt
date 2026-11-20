package com.sagomungchi.core.report.client

import com.sagomungchi.core.report.domain.ReportJobStatus
import java.time.LocalDate
import java.util.UUID

/**
 * P25 고정 대화(#392)가 쓰는 일일 리포트 한 회차의 숫자·판정 요약(#814). [ReportClient.pinned]가 작업의 학생·기간·주기·회차와
 * 맞는지, 지표·문제·판정 요소가 report-api 계약 모양인지 검사한 뒤에만 만든다. 답변·되묻기·인용·서술 같은 원문은 담지 않는다.
 */
data class PinnedReport(val reportId: UUID, val revision: Int, val status: ReportJobStatus, val date: LocalDate,
    val metrics: List<Metric>, val problems: List<Problem>) {
    /** `metrics[]` 한 항목: 표시 이름과 0 이상 개수. */
    data class Metric(val label: String, val count: Int)

    /** `problems[]` 한 항목. [context]·[judgment]는 report-api 열거값 또는 null. */
    data class Problem(val title: String, val context: String?, val judgment: String?, val elements: List<Element>)

    /** 판정 요소: 이름과 충족 여부. */
    data class Element(val label: String, val satisfied: Boolean)

    companion object {
        val CONTEXTS = setOf("THEME_DAY", "THEME_REVIEW", "EXTRA")
        val JUDGMENTS = setOf("CORRECT", "PARTIAL", "RETHINK", "HELD")
    }
}
