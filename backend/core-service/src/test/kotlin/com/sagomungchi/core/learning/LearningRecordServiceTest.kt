package com.sagomungchi.core.learning

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.web.IdempotencyService
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import com.sagomungchi.core.learning.client.LearningClient
import com.sagomungchi.core.learning.client.LearningHttpProperties
import com.sagomungchi.core.learning.client.LearningRecordClient
import com.sagomungchi.core.learning.service.LearningRecordService
import com.sagomungchi.core.learning.service.LearningProxyService
import io.github.resilience4j.circuitbreaker.CircuitBreaker
import org.junit.jupiter.api.Test
import org.mockito.Mockito.mock
import org.springframework.web.client.RestClient
import java.time.Duration
import java.util.UUID
import kotlin.test.*

class LearningRecordServiceTest {
    private fun client(stub: LearningHttpStub, timeout: Duration = Duration.ofSeconds(2)) = LearningClient(
        InternalRestClientFactory(AppProperties(AppProperties.Internal("server-secret", Duration.ofSeconds(1), Duration.ofSeconds(30)),
            mapOf("learning" to stub.url)), RestClient.builder()), LearningHttpProperties(timeout))
    private fun service(client: LearningClient) = LearningRecordService(LearningRecordClient(client, jacksonObjectMapper()), mock(com.sagomungchi.core.guardianship.service.StudentAccessService::class.java), mock(StudentLearningContextService::class.java))
    private fun parent(child: UUID) = UserContext(UUID.randomUUID().toString(), "PARENT", setOf(child.toString()), null)

    @Test fun `records entry checks parent and scope before HTTP without broadening student proxy`() = LearningHttpStub().use { stub ->
        val child=UUID.randomUUID();val client=client(stub);val service=service(client)
        try {
            val contexts=listOf<UserContext?>(null, parent(child).copy(role="STUDENT"), parent(child).copy(role="ADMIN"),
                parent(child).copy(userId=null), parent(child).copy(studentScope=emptySet()))
            for (context in contexts) {
                if(context==null) UserContextHolder.clear() else UserContextHolder.set(context)
                assertEquals(403,assertFailsWith<BusinessException> { service.exists(child) }.status.value())
            }
            UserContextHolder.set(parent(child))
            val proxy=LearningProxyService(client,mock(IdempotencyService::class.java),mock(StudentLearningContextService::class.java))
            assertEquals("FORBIDDEN",assertFailsWith<BusinessException> { proxy.exchange("GET","/missions") }.code)
            assertTrue(stub.requests.isEmpty())
        } finally { UserContextHolder.clear() }
    }
    @Test fun `existing circuit open rejects records without another HTTP and half open records recover it`() = LearningHttpStub().use { stub ->
        val child=UUID.randomUUID();val client=client(stub);val service=service(client)
        UserContextHolder.set(parent(child))
        try {
            stub.respond={ LearningHttpStub.Reply(503) }
            repeat(20) { client.exchange("GET","/missions") }
            assertEquals(CircuitBreaker.State.OPEN,client.circuit.state)
            assertNull(service.exists(child));assertEquals(20,stub.requests.size)
            client.circuit.transitionToHalfOpenState()
            stub.respond={ LearningHttpStub.Reply(body="{\"studentId\":\"$child\",\"hasRecords\":true}") }
            assertEquals(true,service.exists(child))
            assertEquals(CircuitBreaker.State.CLOSED,client.circuit.state)
        } finally { UserContextHolder.clear() }
    }
    @Test fun `records server failures open the same circuit used by student proxy`() = LearningHttpStub().use { stub ->
        val child=UUID.randomUUID();val client=client(stub);val service=service(client)
        val context=parent(child);UserContextHolder.set(context)
        try {
            stub.respond={ LearningHttpStub.Reply(502) }
            repeat(20) { assertNull(service.exists(child)) }
            assertEquals(CircuitBreaker.State.OPEN,client.circuit.state)
            UserContextHolder.set(context.copy(role="STUDENT"))
            val proxy=LearningProxyService(client,mock(IdempotencyService::class.java),mock(StudentLearningContextService::class.java))
            assertEquals("LEARNING_CIRCUIT_OPEN",assertFailsWith<BusinessException> { proxy.exchange("GET","/attempts/test") }.code)
            assertEquals(20,stub.requests.size)
        } finally { UserContextHolder.clear() }
    }
    @Test fun `record timeout is unavailable and records one failed call without retry`() = LearningHttpStub().use { stub ->
        val child=UUID.randomUUID();val client=client(stub,Duration.ofMillis(100));val service=service(client)
        UserContextHolder.set(parent(child))
        try {
            stub.respond={ Thread.sleep(400); LearningHttpStub.Reply() }
            assertNull(service.exists(child))
            assertEquals(1,stub.requests.size)
            assertEquals(1,client.circuit.metrics.numberOfFailedCalls)
        } finally { UserContextHolder.clear() }
    }
}
