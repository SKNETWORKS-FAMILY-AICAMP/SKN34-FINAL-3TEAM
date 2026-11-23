package com.sagomungchi.core.memorybook.client

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.memorybook.domain.MemoryBookDownload
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import org.springframework.web.client.RestClientException
import org.springframework.web.client.RestClientResponseException
import java.net.URI
import java.time.OffsetDateTime
import java.util.UUID

/** report 파일 주소 응답. 업무상 판단(404·409를 어떤 공개 오류로 바꿀지)은 application이 한다(아키텍처 2.1 client 오류 범위) */
sealed interface MemoryBookFileResult {
    data class Url(val download: MemoryBookDownload) : MemoryBookFileResult
    data object Missing : MemoryBookFileResult
    data object Deleting : MemoryBookFileResult
}

/**
 * report-api 그림책 파일 주소 (docs/proposals/memory-book.md 7.2, 미도입 시험 구현).
 * 호출 동안만 학생 범위를 그 학생 1명으로 좁힌다. 모양 오류 502, 연결·5xx 503
 */
@Component
class MemoryBookReportClient(factory: InternalRestClientFactory, private val json: ObjectMapper) {
    private val http = factory.create("report")

    fun fileUrl(studentId: UUID, bookId: UUID): MemoryBookFileResult {
        val context = UserContextHolder.current()
        UserContextHolder.set(context.copy(studentScope = setOf(studentId.toString())))
        try {
            val body = try {
                http.get().uri("/internal/students/{student}/memory-books/{book}/files/pdf", studentId, bookId)
                    .retrieve().body(String::class.java)
            } catch (ex: RestClientResponseException) {
                val code = runCatching { json.readTree(ex.responseBodyAsString)?.get("code")?.textValue() }.getOrNull()
                return when {
                    ex.statusCode.value() == 404 -> MemoryBookFileResult.Missing
                    ex.statusCode.value() == 409 && code == "DELETION_IN_PROGRESS" -> MemoryBookFileResult.Deleting
                    else -> throw unavailable()
                }
            } catch (_: RestClientException) { throw unavailable() }
            return try {
                val node = json.readTree(body)
                val url = node["url"].textValue()
                val uri = URI(url)
                require(uri.scheme in setOf("http", "https") && !uri.host.isNullOrBlank() && uri.userInfo == null)
                val expiresAt = node["expiresAt"].textValue().also { OffsetDateTime.parse(it) }
                MemoryBookFileResult.Url(MemoryBookDownload(url, expiresAt))
            } catch (_: Exception) { throw invalid() }
        } finally { UserContextHolder.set(context) }
    }

    private fun unavailable() = BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "REPORT_UNAVAILABLE", "리포트 서비스에 연결할 수 없습니다.")
    private fun invalid() = BusinessException(HttpStatus.BAD_GATEWAY, "REPORT_CONTRACT_INVALID", "리포트 서비스 응답 형식을 확인할 수 없습니다.")
}
