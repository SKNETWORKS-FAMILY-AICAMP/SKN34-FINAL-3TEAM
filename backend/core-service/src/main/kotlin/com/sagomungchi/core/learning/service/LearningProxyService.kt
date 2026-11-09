package com.sagomungchi.core.learning.service

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core._common.web.IdempotencyService
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import com.sagomungchi.core.learning.client.LearningClient
import com.sagomungchi.core.payment.service.ProductEntitlementService
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

@Service
class LearningProxyService(private val client: LearningClient, private val idempotency: IdempotencyService,
                           private val students: StudentLearningContextService,
                           private val entitlements: ProductEntitlementService, private val json: ObjectMapper) {
    fun exchange(method: String, path: String, query: String? = null, body: ByteArray? = null,
                 ifMatch: String? = null, key: UUID? = null) = run {
        val context = verifiedStudent()
        val missionQuery = method == "GET" && (path == "/missions" || path.startsWith("/missions/"))
        val internalQuery = if (missionQuery) listOfNotNull(profileQuery(context), query).joinToString("&") else query
        val operation = { client.exchange(method, path, internalQuery, body, ifMatch, key?.toString()) }
        if (key == null) operation() else idempotency.execute(key, UUID.fromString(context.userId),
            "$method /api/v1$path", context.studentScope, requireNotNull(body), operation)
    }

    /**
     * 시도 시작 (#387, api-spec 2.2·2.11). `context` 생략은 `EXTRA`(생각 유형별 고르기). 판정은 [ProductEntitlementService]가 하고
     * learning에는 학년·시연 여부와 `{context}`를 넘긴다(요일·되돌아보기 검사는 learning). 신규 `201`만 사용량을 기록하고 이어하기 `200`은 기록하지 않는다.
     */
    fun startAttempt(mission: UUID, attemptContext: String): HttpExchangeResult {
        val context = verifiedStudent()
        val student = UUID.fromString(context.studentScope.single())
        val query = profileQuery(context)
        val permit = entitlements.missionStart(student, attemptContext, mission) { attempt -> inProgress(attempt, mission) }
        val response = client.exchange("POST", "/missions/$mission/attempts", query,
            json.writeValueAsBytes(mapOf("context" to attemptContext)))
        if (response.status == 201) {
            val attempt = attemptId(response)
            // 기록 실패는 학습 응답을 바꾸지 않는다(다시 시작하면 200 이어하기라 학생이 막히지 않음). 원인은 로그로 추적
            if (attempt == null) log.warn("learning 201 attempt without attemptId; mission usage not recorded: mission={}", mission)
            else try { entitlements.missionStarted(permit, attempt, mission) } catch (error: RuntimeException) {
                log.error("mission usage not recorded: attempt={}, context={}", attempt, attemptContext, error)
            }
        }
        return response
    }

    /** 이번 주(KST) 학년군 테마 (#387, api-spec 2.11). #439 새 필드(`outro`·이미지 URL·`introSeen`·`outroSeen`)도 바꾸지 않고 전달. #389 학습 완료 적립 보충은 이 응답을 받은 뒤에 붙인다 */
    fun weeklyTheme(): HttpExchangeResult {
        val context = verifiedStudent()
        return client.exchange("GET", "/students/${context.studentScope.single()}/weekly-theme", themeQuery(context))
    }

    /** 토·일 되돌아보기 열람 기록 (#387, 멱등은 learning). #389 되돌아보기·완주 적립은 `{firstViewThisWeek, completed}` 응답 뒤에 붙인다 */
    fun reviewViewed(): HttpExchangeResult {
        val context = verifiedStudent()
        return client.exchange("POST", "/students/${context.studentScope.single()}/weekly-theme/review-views", themeQuery(context))
    }

    /**
     * 시작·종료 이야기 열람 기록 (#439, api-spec 2.11). 본문 `{kind: INTRO|OUTRO}`만 core가 확인해 다시 만들어 넘기고
     * 요일(INTRO 월요일·OUTRO 토요일)·주 1회 멱등은 learning이 `date`로 판정한다. 응답·오류는 그대로 전달
     */
    fun storyViewed(body: ByteArray): HttpExchangeResult {
        val context = verifiedStudent()
        val node = try { json.readTree(body) } catch (_: Exception) { null }
        val kind = node?.takeIf { it.isObject && it.size() == 1 }?.path("kind")?.takeIf { it.isTextual }?.asText()
        if (kind !in STORY_KINDS) throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "kind는 INTRO 또는 OUTRO여야 합니다.")
        return client.exchange("POST", "/students/${context.studentScope.single()}/weekly-theme/story-views", themeQuery(context),
            json.writeValueAsBytes(mapOf("kind" to kind)))
    }

    private fun verifiedStudent() = UserContextHolder.currentOrNull()?.takeIf {
        it.role == "STUDENT" && it.userId != null && it.studentScope.size == 1
    } ?: throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 학생 세션이 필요합니다.")

    private fun linked(context: UserContext) =
        students.requireLinked(UUID.fromString(context.userId), UUID.fromString(context.studentScope.single()))

    private fun profileQuery(context: UserContext) =
        linked(context).let { student -> listOf("grade=${student.grade}", "demo=${student.demo}").joinToString("&") }

    /** 학년군은 core 학년에서 정한다(초3~4 `G3_4`, 초5~6 `G5_6`). 날짜는 KST 오늘이라 무료 한도와 같은 날을 쓴다 */
    private fun themeQuery(context: UserContext): String {
        val band = if (linked(context).grade <= 4) "G3_4" else "G5_6"
        return "gradeBand=$band&date=${entitlements.today()}"
    }

    /** 한도 도달 뒤 이어하기 확인: 마지막 기록 시도가 이 미션의 진행 중 시도면 learning이 그 시도를 200으로 돌려준다 */
    private fun inProgress(attempt: UUID, mission: UUID): Boolean {
        val response = client.exchange("GET", "/attempts/$attempt")
        if (response.status != 200) return false
        val node = try { json.readTree(response.body) } catch (_: Exception) { null } ?: return false
        return node.path("status").asText() == "IN_PROGRESS" && node.path("mission").path("id").asText() == mission.toString()
    }

    private fun attemptId(response: HttpExchangeResult) = try {
        UUID.fromString(json.readTree(response.body).path("attemptId").asText())
    } catch (_: Exception) { null }

    private companion object {
        val log = LoggerFactory.getLogger(LearningProxyService::class.java)
        val STORY_KINDS = setOf("INTRO", "OUTRO")
    }
}
