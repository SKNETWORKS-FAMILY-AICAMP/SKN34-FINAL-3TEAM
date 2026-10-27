package com.sagomungchi.core.guardianship.client

import com.fasterxml.jackson.databind.JsonNode
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core.guardianship.domain.ChildRecords
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClientException
import java.util.UUID

/** No learning DB access, retries or manufactured NO_RECORD response. */
@Component
class ChildRecordsClient(factory: InternalRestClientFactory) {
    private val client = factory.create("learning")
    fun records(studentId: UUID): ChildRecords {
        val body = try {
            client.get().uri("/internal/records/students/{id}/exists", studentId)
                .retrieve().body(JsonNode::class.java)
        } catch (_: RestClientException) { return ChildRecords(null, "UNAVAILABLE") }
        val exists = body?.get("hasRecords")
        if (body?.get("studentId")?.asText() != studentId.toString() || exists == null || !exists.isBoolean)
            return ChildRecords(null, "UNAVAILABLE")
        return ChildRecords(exists.booleanValue(), "AVAILABLE")
    }
}
