package com.sagomungchi.core.report

import com.sagomungchi.core._common.exception.DomainException
import com.sagomungchi.core._common.exception.ErrorKind
import com.sagomungchi.core.report.domain.ReportTemplateSettings
import org.junit.jupiter.api.Test
import kotlin.test.*

class ReportTemplateSettingsTest {
    @Test fun `전체 섹션 순열과 허용된 강조 및 톤만 지원한다`() {
        assertEquals("EASY", ReportTemplateSettings(sectionOrder = ReportTemplateSettings.SECTIONS.reversed(),
            highlightMetrics = listOf("ATTEMPTS"), tone = "EASY").validate().tone)
        for (invalid in listOf(
            ReportTemplateSettings(sectionOrder = listOf("quotes")),
            ReportTemplateSettings(sectionOrder = List(6) { "quotes" }),
            ReportTemplateSettings(highlightMetrics = listOf("SCORE")),
            ReportTemplateSettings(highlightMetrics = listOf("ATTEMPTS", "ATTEMPTS")),
            ReportTemplateSettings(tone = "ARBITRARY"),
        )) assertEquals(ErrorKind.INVALID to "INVALID_TEMPLATE_SETTINGS", assertFailsWith<DomainException> { invalid.validate() }.let { it.kind to it.code })
    }
}
