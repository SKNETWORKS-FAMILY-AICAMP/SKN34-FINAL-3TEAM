package com.sagomungchi.core.conversation.client

import com.sagomungchi.core.report.domain.ReportTemplateSettings

/**
 * ai `/internal/analysis/report-template` 응답(TemplateProposal, #280·#824). [AiClient.reportTemplate]가 칸 모양을 검사한 뒤
 * 되묻기 문장 하나나 설정 세 칸 중 하나로만 만든다. 허용 섹션·지표·말투 검사는 [ReportTemplateSettings.validate]가 한다.
 */
sealed interface TemplateProposal {
    /** 1~400자 되묻기. 이때 설정은 없다. */
    data class Clarification(val text: String) : TemplateProposal
    /** `sectionOrder`·`highlightMetrics`·`tone` 세 칸만 있는 설정 변경안. */
    data class Settings(val settings: ReportTemplateSettings) : TemplateProposal
}
