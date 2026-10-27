package com.sagomungchi.core._common.web

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.web.repository.IdempotencyRepository
import org.springframework.http.HttpStatus
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import org.springframework.stereotype.Service
import org.springframework.transaction.support.TransactionSynchronizationManager
import java.security.MessageDigest
import java.util.Base64
import java.util.UUID

@Service
class IdempotencyService(private val repository: IdempotencyRepository, private val json: ObjectMapper) {
    fun execute(key: UUID, user: UUID, endpoint: String, studentScope: Set<String>, body: ByteArray,
                operation: () -> HttpExchangeResult): HttpExchangeResult {
        check(!TransactionSynchronizationManager.isActualTransactionActive()) { "External HTTP must run outside a transaction" }
        val digest = MessageDigest.getInstance("SHA-256")
        // A parent account can enter different children: cached responses must not bypass their scope.
        digest.update(studentScope.sorted().joinToString(",").toByteArray())
        digest.update(0.toByte())
        val hash = digest.digest(body).joinToString("") { "%02x".format(it) }
        val lease = storage { repository.acquire(key, user) } ?: run {
            storage { repository.findUnexpired(key, user) }?.let { record ->
                requireSameRequest(record.endpoint == endpoint && record.requestHash == hash)
            }
            throw RetryableRequestException(HttpStatus.CONFLICT, "IDEMPOTENCY_IN_PROGRESS", "같은 요청을 처리 중입니다.", 1)
        }
        try {
            val record = storage { repository.prepare(lease, endpoint, hash) }
            requireSameRequest(record.endpoint == endpoint && record.requestHash == hash)
            record.status?.let { status ->
                return storage {
                    val envelope = json.readTree(requireNotNull(record.response))
                    HttpExchangeResult(status, envelope["headers"].properties().associate { (name, values) ->
                        name to values.map { it.asText() }
                    }, Base64.getDecoder().decode(envelope["body"].asText()))
                }
            }
            val result = operation() // auto-commit session lock only; no transaction/row lock
            if (result.status in 200..499) storage {
                val envelope = json.writeValueAsString(mapOf("headers" to result.headers, "body" to Base64.getEncoder().encodeToString(result.body)))
                repository.complete(lease, result.status, envelope)
            }
            return result
        } finally { storage { lease.close() } }
    }

    fun deleteExpired() = storage { repository.deleteExpired() }

    private fun requireSameRequest(matches: Boolean) {
        if (!matches) throw BusinessException(HttpStatus.UNPROCESSABLE_ENTITY, "IDEMPOTENCY_KEY_REUSED", "같은 키에 다른 요청을 사용할 수 없습니다.")
    }

    private fun <T> storage(block: () -> T): T = try { block() } catch (ex: Exception) {
        throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "IDEMPOTENCY_UNAVAILABLE", "요청 결과를 확인하지 못했습니다. 같은 키로 다시 요청해 주세요.")
    }
}

@Component
class IdempotencyCleanup(private val service: IdempotencyService) {
    @Scheduled(fixedDelayString = "\${app.web.idempotency-cleanup-interval:3600000}", initialDelayString = "3600000")
    fun cleanup() { service.deleteExpired() }
}
