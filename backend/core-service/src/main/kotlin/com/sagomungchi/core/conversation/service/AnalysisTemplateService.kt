package com.sagomungchi.core.conversation.service

import com.fasterxml.jackson.databind.JsonNode
import com.sagomungchi.core.conversation.client.AiClient
import org.springframework.stereotype.Service

/** #279: other features request the AI report-template proposal through this service, not AiClient. */
@Service
class AnalysisTemplateService(private val ai: AiClient) {
    fun reportTemplate(request: Any): JsonNode = ai.reportTemplate(request)
}
