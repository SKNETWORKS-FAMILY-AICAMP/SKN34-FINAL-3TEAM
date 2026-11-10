package com.sagomungchi.core.community.client

import com.fasterxml.jackson.core.JsonProcessingException
import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core._common.client.LearningClient
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import java.net.URLEncoder
import java.util.UUID

/**
 * learning 커뮤니티 내부 API(api-spec 4.1, #386) 클라이언트. 잠금을 쥔 DB 트랜잭션 안에서는 부르지 않는다(공개 전환은 커밋 뒤).
 * 호출 주체는 요청마다 명시한다: 학생 본인 조회·반응은 STUDENT, 학부모 자녀 조회는 PARENT, 공유·공개 전환·검토는 SYSTEM.
 */
@Component
class CommunityClient(private val http: LearningClient, private val json: ObjectMapper) {
    data class SharedPost(val postId: UUID, val created: Boolean)
    data class PostDetail(val postId: UUID, val studentId: UUID, val missionId: UUID?, val status: String, val answer: JsonNode?)

    /** 학습 완료 시도 공유. 201 새로 공유, 200 이미 있음(학생·미션당 1개). 그 밖의 응답은 공유하지 않은 것으로 본다. */
    fun createPost(studentId: UUID, attemptId: UUID): SharedPost? = acting("SYSTEM", null, studentId) {
        val response = http.exchange("POST", "/community/posts", body = json.writeValueAsBytes(mapOf("studentId" to studentId, "attemptId" to attemptId)))
        if (response.status !in setOf(200, 201)) return@acting null
        val postId = uuidOrNull(read(response).path("postId")) ?: invalid()
        SharedPost(postId, response.status == 201)
    }

    fun missionPosts(missionId: UUID, viewer: UUID, viewerUser: UUID, seed: String, page: Int, size: Int): JsonNode =
        acting("STUDENT", viewerUser, viewer) {
            val query = "viewerStudentId=$viewer&seed=${URLEncoder.encode(seed, Charsets.UTF_8)}&page=$page&size=$size"
            read(checked(http.exchange("GET", "/community/missions/$missionId/posts", query)))
        }

    fun studentPosts(studentId: UUID, role: String, user: UUID): JsonNode = acting(role, user, studentId) {
        read(checked(http.exchange("GET", "/community/students/$studentId/posts")))
    }

    /** 반응 생성(true)·이미 있음(false). 취소는 결과 없음. */
    fun react(postId: UUID, studentId: UUID, user: UUID, reaction: String, on: Boolean): Boolean = acting("STUDENT", user, studentId) {
        val response = checked(http.exchange(if (on) "PUT" else "DELETE", "/community/posts/$postId/reactions/$reaction", "studentId=$studentId"))
        on && response.body.isNotEmpty() && read(response).path("created").asBoolean(false)
    }

    fun setVisibility(studentId: UUID, visible: Boolean, reason: String) = acting("SYSTEM", null, studentId) {
        checked(http.exchange("PUT", "/students/$studentId/community-visibility",
            body = json.writeValueAsBytes(mapOf("visible" to visible, "reason" to reason))))
        Unit
    }

    fun moderate(postId: UUID, status: String, errorReportId: UUID) = acting("SYSTEM", null, null) {
        checked(http.exchange("PUT", "/community/posts/$postId/moderation",
            body = json.writeValueAsBytes(mapOf("status" to status, "errorReportId" to errorReportId))))
        Unit
    }

    /** 신고 대상 확인·관리자 원문 열람. 없는(삭제된) 공유물은 null. */
    fun post(postId: UUID): PostDetail? = acting("SYSTEM", null, null) {
        val response = http.exchange("GET", "/community/posts/$postId")
        if (response.status == 404) return@acting null
        val body = read(checked(response))
        val status = body.path("status").asText()
        if (uuidOrNull(body.path("postId")) != postId || status !in com.sagomungchi.core.community.domain.Community.POST_STATUSES) invalid()
        PostDetail(postId, uuidOrNull(body.path("studentId")) ?: invalid(), uuidOrNull(body.path("missionId")), status,
            body.get("answer")?.takeUnless { it.isNull })
    }

    private fun checked(response: HttpExchangeResult): HttpExchangeResult {
        if (response.status in 200..299) return response
        // 공개 오류 코드만 그대로 전달하고, 나머지 공급자 본문은 노출하지 않는다.
        val code = problemCode(response)
        PUBLIC_ERRORS[response.status to code]?.let { throw BusinessException(HttpStatus.valueOf(response.status), code!!, it) }
        throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE, "COMMUNITY_UNAVAILABLE", "커뮤니티 처리를 확인하지 못했습니다.")
    }

    private fun problemCode(response: HttpExchangeResult): String? = try {
        json.readTree(response.body)?.path("code")?.takeIf { it.isTextual }?.asText()
    } catch (_: JsonProcessingException) { null }

    private fun read(response: HttpExchangeResult): JsonNode = try {
        json.readTree(response.body)?.takeIf { it.isObject } ?: invalid()
    } catch (_: JsonProcessingException) { invalid() }

    private fun uuidOrNull(node: JsonNode): UUID? = if (!node.isTextual) null else try { UUID.fromString(node.asText()) } catch (_: IllegalArgumentException) { null }

    private fun <T> acting(role: String, user: UUID?, student: UUID?, block: () -> T): T {
        val previous = UserContextHolder.currentOrNull()
        UserContextHolder.set(UserContext(user?.toString(), role, setOfNotNull(student?.toString()), previous?.traceparent))
        return try { block() } finally { if (previous == null) UserContextHolder.clear() else UserContextHolder.set(previous) }
    }

    private fun invalid(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY, "COMMUNITY_INVALID_RESPONSE", "커뮤니티 응답 계약이 올바르지 않습니다.")

    companion object {
        private val PUBLIC_ERRORS = mapOf(
            (403 to "COMMUNITY_LOCKED") to "이 미션을 마무리하면 친구들 생각을 볼 수 있어요.",
            (404 to "COMMUNITY_POST_NOT_FOUND") to "볼 수 없는 공유물입니다.",
            (404 to "NOT_FOUND") to "미션 또는 공유물을 찾을 수 없습니다.",
            (409 to "COMMUNITY_OWN_POST") to "내 공유물에는 반응할 수 없어요.",
            (400 to "VALIDATION_FAILED") to "입력값을 확인해 주세요.",
        )
    }
}
