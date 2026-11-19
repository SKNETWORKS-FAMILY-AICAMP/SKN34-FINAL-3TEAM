package com.sagomungchi.core.community.client

import com.fasterxml.jackson.core.JsonProcessingException
import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core._common.client.LearningClient
import com.sagomungchi.core.community.domain.Community
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import java.net.URLEncoder
import java.time.OffsetDateTime
import java.time.format.DateTimeParseException
import java.util.UUID

/**
 * learning 커뮤니티 내부 API(api-spec 4.1, #386) 클라이언트. 잠금을 쥔 DB 트랜잭션 안에서는 부르지 않는다(공개 전환은 커밋 뒤).
 * 호출 주체는 요청마다 명시한다: 학생 본인 조회·반응은 STUDENT, 학부모 자녀 조회는 PARENT, 공유·공개 전환·검토는 SYSTEM.
 */
@Component
class CommunityClient(private val http: LearningClient, private val json: ObjectMapper) {
    data class SharedPost(val postId: UUID, val created: Boolean)
    /** 신고 대상 확인·관리자 원문. [answer]는 [sharedAnswer]로 모양을 확인한 learning 원문이다(#825). */
    data class PostDetail(val postId: UUID, val studentId: UUID, val missionId: UUID?, val status: String, val answer: JsonNode)

    /**
     * 미션 공유물 목록 한 항목. 학생 ID는 service가 작성자 표시로 바꾼 뒤 버린다. 답변은 모양(공개 계약 `CommunityAnswer`)을
     * 확인한 learning 원문 그대로다(#825). [createdAt]은 date-time으로 읽히는 것을 확인한 learning 문자열 그대로다(#814).
     */
    data class MissionPost(val postId: UUID, val studentId: UUID, val answer: JsonNode, val myReactions: List<String>, val createdAt: String?)

    /**
     * 내 공유물·자녀 공유물 한 항목. [status]는 learning 상태(`Community.POST_STATUSES`), 반응 수는 `Community.REACTIONS` 전부를
     * 0 이상 정수로 채운다. 미션 ID·제목·작성 시각은 client가 형식을 확인한 값만 담는다(#814). 답변은 모양을 확인한 원문이다(#825).
     */
    data class StudentPost(val postId: UUID, val missionId: UUID?, val missionTitle: String?, val answer: JsonNode,
        val status: String, val reactions: Map<String, Int>, val createdAt: String?)

    /** 학습 완료 시도 공유. 201 새로 공유, 200 이미 있음(학생·미션당 1개). 그 밖의 응답은 공유하지 않은 것으로 본다. */
    fun createPost(studentId: UUID, attemptId: UUID): SharedPost? = acting("SYSTEM", null, studentId) {
        val response = http.exchange("POST", "/community/posts", body = json.writeValueAsBytes(mapOf("studentId" to studentId, "attemptId" to attemptId)))
        if (response.status !in setOf(200, 201)) return@acting null
        val postId = uuidOrNull(read(response).path("postId")) ?: invalid()
        SharedPost(postId, response.status == 201)
    }

    /**
     * `items[]`의 공유물·작성자 ID가 UUID가 아니거나, 답변이 [sharedAnswer] 모양이 아니거나, 작성 시각이 date-time·null이 아니면
     * 502 `COMMUNITY_INVALID_RESPONSE`. 내 반응은 알려진 종류만 남긴다.
     */
    fun missionPosts(missionId: UUID, viewer: UUID, viewerUser: UUID, seed: String, page: Int, size: Int): List<MissionPost> =
        acting("STUDENT", viewerUser, viewer) {
            val query = "viewerStudentId=$viewer&seed=${URLEncoder.encode(seed, Charsets.UTF_8)}&page=$page&size=$size"
            items(read(checked(http.exchange("GET", "/community/missions/$missionId/posts", query)))).map { item ->
                MissionPost(uuid(item.path("postId")), uuid(item.path("studentId")), sharedAnswer(item.path("answer")),
                    reactions(item.path("myReactions")), dateTimeOrNull(item.path("createdAt")))
            }
        }

    /**
     * `items[]`의 공유물 ID가 UUID가 아니거나, 상태가 알려진 값이 아니거나, 미션 ID(UUID|null)·미션 제목(문자열|null)·
     * 작성 시각(date-time|null)·반응 수(0 이상 정수)·답변([sharedAnswer])이 형식에 맞지 않으면 502 `COMMUNITY_INVALID_RESPONSE`
     * (#814·#825). 빠진 반응 수는 0.
     */
    fun studentPosts(studentId: UUID, role: String, user: UUID): List<StudentPost> = acting(role, user, studentId) {
        items(read(checked(http.exchange("GET", "/community/students/$studentId/posts")))).map { item ->
            val status = item.path("status").asText()
            if (status !in Community.POST_STATUSES) invalid()
            StudentPost(uuid(item.path("postId")), nullable(item.path("missionId")) { uuid(it) },
                nullable(item.path("missionTitle")) { if (it.isTextual) it.textValue() else invalid() }, sharedAnswer(item.path("answer")), status,
                reactionCounts(item.path("reactions")), dateTimeOrNull(item.path("createdAt")))
        }
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

    /**
     * 친구 방 구경(#708)용 작성자 찾기 + 열람 검사(learning #707). 열람자 본인(STUDENT)으로 부르고 작성자 학생 ID를 돌려준다.
     * learning 공개 오류(403 잠금·404 없음·409 본인 글)는 그대로 전달한다.
     */
    fun postAuthor(postId: UUID, viewer: UUID, viewerUser: UUID): UUID = acting("STUDENT", viewerUser, viewer) {
        val body = read(checked(http.exchange("GET", "/community/posts/$postId/author", "viewerStudentId=$viewer")))
        if (uuidOrNull(body.path("postId")) != postId) invalid()
        uuidOrNull(body.path("studentId")) ?: invalid()
    }

    /** 신고 대상 확인·관리자 원문 열람. 없는(삭제된) 공유물은 null. 답변이 [sharedAnswer] 모양이 아니면 502(#825). */
    fun post(postId: UUID): PostDetail? = acting("SYSTEM", null, null) {
        val response = http.exchange("GET", "/community/posts/$postId")
        if (response.status == 404) return@acting null
        val body = read(checked(response))
        val status = body.path("status").asText()
        if (uuidOrNull(body.path("postId")) != postId || status !in Community.POST_STATUSES) invalid()
        PostDetail(postId, uuidOrNull(body.path("studentId")) ?: invalid(), uuidOrNull(body.path("missionId")), status,
            sharedAnswer(body.path("answer")))
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

    private fun items(body: JsonNode): List<JsonNode> = body.path("items").takeIf { it.isArray }?.toList() ?: invalid()
    private fun uuid(node: JsonNode): UUID = try { UUID.fromString(node.asText()) } catch (_: IllegalArgumentException) { invalid() }
    /** 빠지거나 null이면 null, 있으면 [parse]로 읽는다(형식이 틀리면 [parse]가 502). */
    private fun <T> nullable(node: JsonNode, parse: (JsonNode) -> T): T? = if (node.isMissingNode || node.isNull) null else parse(node)
    /** date-time 문자열은 learning 값 그대로 돌려준다. 문자열이 아니거나 읽히지 않으면 502. */
    private fun dateTimeOrNull(node: JsonNode): String? = nullable(node) {
        if (!it.isTextual) invalid()
        try { OffsetDateTime.parse(it.textValue()); it.textValue() } catch (_: DateTimeParseException) { invalid() }
    }
    /** 반응 수 객체. 빠진 객체·빠진 종류는 0이고, 있는 값은 0 이상 int 정수만 받는다(null·음수·문자열·소수는 502). */
    private fun reactionCounts(node: JsonNode): Map<String, Int> {
        if (!node.isMissingNode && !node.isObject) invalid()
        return Community.REACTIONS.associateWith { reaction ->
            val count = node.path(reaction)
            when {
                count.isMissingNode -> 0
                count.isIntegralNumber && count.canConvertToInt() && count.intValue() >= 0 -> count.intValue()
                else -> invalid()
            }
        }
    }
    /**
     * 공유 답변(공개 계약 `CommunityAnswer`, api-spec 2.9, #825). `{inputType, text, content}` 세 칸만 있고, `text`는 문자열,
     * `content`는 그 입력 방식에 쓰는 칸만(learning `AnswerContent.only`) 있어야 한다. 확인한 learning 원문을 그대로 돌려준다.
     * 빠짐·null·모르는 입력 방식·다른 입력 방식 칸·타입 오류는 502. 빈 글·목록 개수는 learning 제출 검사가 맡는다.
     */
    private fun sharedAnswer(node: JsonNode): JsonNode {
        if (!node.isObject || node.size() != 3 || !node.path("text").isTextual) invalid()
        val content = node.path("content")
        val fields = CONTENT_FIELDS[node.path("inputType").takeIf { it.isTextual }?.textValue()] ?: invalid()
        if (!content.isObject || fieldNames(content) != fields.keys || fields.any { (name, valid) -> !valid(content.path(name)) }) invalid()
        return node
    }
    private fun reactions(node: JsonNode) = if (node.isArray) node.map { it.asText() }.filter { it in Community.REACTIONS } else emptyList()
    private fun uuidOrNull(node: JsonNode): UUID? = if (!node.isTextual) null else try { UUID.fromString(node.asText()) } catch (_: IllegalArgumentException) { null }

    private fun <T> acting(role: String, user: UUID?, student: UUID?, block: () -> T): T {
        val previous = UserContextHolder.currentOrNull()
        UserContextHolder.set(UserContext(user?.toString(), role, setOfNotNull(student?.toString()), previous?.traceparent))
        return try { block() } finally { if (previous == null) UserContextHolder.clear() else UserContextHolder.set(previous) }
    }

    private fun invalid(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY, "COMMUNITY_INVALID_RESPONSE", "커뮤니티 응답 계약이 올바르지 않습니다.")

    companion object {
        private fun fieldNames(node: JsonNode) = node.fieldNames().asSequence().toSet()
        private val text: (JsonNode) -> Boolean = { it.isTextual }
        private val texts: (JsonNode) -> Boolean = { it.isArray && it.all(text) }
        /** 논술 4칸: 주장·까닭 정확히 2개·반대 의견에 답하기 */
        private val essay: (JsonNode) -> Boolean = {
            it.isObject && fieldNames(it) == setOf("claim", "reasons", "rebuttal") && text(it.path("claim")) &&
                texts(it.path("reasons")) && it.path("reasons").size() == 2 && text(it.path("rebuttal"))
        }
        private val assignments: (JsonNode) -> Boolean = { list ->
            list.isArray && list.all { fieldNames(it) == setOf("choiceId", "categoryId") && text(it.path("choiceId")) && text(it.path("categoryId")) }
        }

        /** 입력 방식별 `content` 칸과 검사(api-spec 3.8). 고르기·순서는 같은 모양이다. */
        private val CONTENT_FIELDS: Map<String, Map<String, (JsonNode) -> Boolean>> = mapOf(
            "NARRATIVE" to mapOf("text" to text),
            "SOLUTION_STEPS" to mapOf("finalAnswer" to text, "steps" to texts),
            "ESSAY" to mapOf("essay" to essay),
            "CHOICE" to mapOf("choiceIds" to texts),
            "ORDERING" to mapOf("choiceIds" to texts),
            "CLASSIFICATION" to mapOf("assignments" to assignments),
        )
        private val PUBLIC_ERRORS = mapOf(
            (403 to "COMMUNITY_LOCKED") to "이 미션을 마무리하면 친구들 생각을 볼 수 있어요.",
            // #550: 큰 질문 정답 고르기 문제는 그 주 엔딩을 본 학생만 열람(learning #484)
            (403 to "COMMUNITY_LOCKED_UNTIL_ENDING") to "이번 주 테마 엔딩을 보면 친구들 생각을 볼 수 있어요.",
            (404 to "COMMUNITY_POST_NOT_FOUND") to "볼 수 없는 공유물입니다.",
            (404 to "NOT_FOUND") to "미션 또는 공유물을 찾을 수 없습니다.",
            (409 to "COMMUNITY_OWN_POST") to "내 공유물에는 반응할 수 없어요.",
            (400 to "VALIDATION_FAILED") to "입력값을 확인해 주세요.",
        )
    }
}
