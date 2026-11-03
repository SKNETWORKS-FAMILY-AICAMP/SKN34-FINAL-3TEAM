package com.sagomungchi.core.report.domain

import com.sagomungchi.core._common.exception.DomainException
import com.sagomungchi.core._common.exception.ErrorKind

data class ReportTemplateSettings(
    val sectionOrder: List<String> = SECTIONS,
    val highlightMetrics: List<String> = emptyList(),
    val tone: String = "DEFAULT",
) {
    fun validate(): ReportTemplateSettings {
        if (sectionOrder.size != SECTIONS.size || sectionOrder.toSet() != SECTIONS.toSet() ||
            highlightMetrics.size != highlightMetrics.toSet().size ||
            !METRICS.containsAll(highlightMetrics) || tone !in setOf("DEFAULT", "EASY", "CONCISE"))
            throw DomainException(ErrorKind.INVALID, "INVALID_TEMPLATE_SETTINGS", "허용되지 않은 리포트 설정입니다.")
        return this
    }
    companion object {
        val SECTIONS = listOf("thinkingTypes", "changes", "reflections", "quotes", "narrative", "eveningQuestion")
        val METRICS = setOf("ATTEMPTS", "COMPLETED", "UNASSISTED")
    }
}
data class ReportTemplateSnapshot(val settings: ReportTemplateSettings, val revision: Long)
