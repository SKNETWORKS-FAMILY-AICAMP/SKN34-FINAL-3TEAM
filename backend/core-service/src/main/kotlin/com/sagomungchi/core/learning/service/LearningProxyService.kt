package com.sagomungchi.core.learning.service

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core._common.web.HttpExchangeResult
import com.sagomungchi.core._common.web.IdempotencyService
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import com.sagomungchi.core.community.service.CommunityService
import com.sagomungchi.core.learning.client.LearningClient
import com.sagomungchi.core.payment.service.ProductEntitlementService
import com.sagomungchi.core.reward.service.ParticipationRewardService
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.time.LocalDate
import java.util.UUID

@Service
class LearningProxyService(private val client: LearningClient, private val idempotency: IdempotencyService,
                           private val students: StudentLearningContextService,
                           private val entitlements: ProductEntitlementService, private val json: ObjectMapper,
                           private val community: CommunityService, private val rewards: ParticipationRewardService) {
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

    /**
     * 돌아보기 저장 = 학습 완료 (api-spec 2.2). 저장 성공(2xx)이나 이미 완료(`409 ATTEMPT_CLOSED`, 같은 사건 재요청)면
     * 시도를 다시 조회해 `COMPLETED`인 미션의 학습 완료 포인트를 적립(#389)하고 커뮤니티 공유를 요청한다(P20).
     * 공유가 만들어졌거나 이미 있으면 공유 포인트도 같은 사건 키로 적립한다. 적립·공유 실패는 learning 응답을 바꾸지 않는다.
     */
    fun reflection(attemptId: UUID, body: ByteArray): HttpExchangeResult {
        val response = exchange("POST", "/attempts/$attemptId/reflection", body = body)
        if (response.status in 200..299 || errorCode(response) == "ATTEMPT_CLOSED") {
            val student = UUID.fromString(verifiedStudent().studentScope.single())
            completedMission(attemptId)?.let { rewards.missionCompleted(student, it) }
            community.shareCompleted(attemptId)?.let { rewards.communityPosted(student, it.postId) }
        }
        return response
    }

    /** 이번 주(KST) 학년군 테마 (#387, api-spec 2.11). 200이면 이번 주 학습 완료한 요일 문제의 누락 적립을 보충한다(#389) */
    fun weeklyTheme(): HttpExchangeResult {
        val context = verifiedStudent()
        val response = client.exchange("GET", "/students/${context.studentScope.single()}/weekly-theme", themeQuery(context))
        if (response.status == 200) rewards.weeklyThemeViewed(UUID.fromString(context.studentScope.single()), response.body)
        return response
    }

    /** 토·일 되돌아보기 열람 기록 (#387, 멱등은 learning). 200 `{firstViewThisWeek, completed}` 뒤 되돌아보기·완주 적립(#389) */
    fun reviewViewed(): HttpExchangeResult {
        val context = verifiedStudent()
        val today = entitlements.today()
        val response = client.exchange("POST", "/students/${context.studentScope.single()}/weekly-theme/review-views",
            themeQuery(context, today))
        if (response.status == 200) rewards.reviewViewed(UUID.fromString(context.studentScope.single()), today, response.body)
        return response
    }

    private fun verifiedStudent() = UserContextHolder.currentOrNull()?.takeIf {
        it.role == "STUDENT" && it.userId != null && it.studentScope.size == 1
    } ?: throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 학생 세션이 필요합니다.")

    private fun linked(context: UserContext) =
        students.requireLinked(UUID.fromString(context.userId), UUID.fromString(context.studentScope.single()))

    private fun profileQuery(context: UserContext) =
        linked(context).let { student -> listOf("grade=${student.learningGrade}", "demo=${student.demo}").joinToString("&") }

    /** 학년군은 core 학년에서 정한다(초3~4 `G3_4`, 초5~6과 중학생 `G5_6`, #432). 날짜는 KST 오늘이라 무료 한도와 같은 날을 쓴다 */
    private fun themeQuery(context: UserContext, date: LocalDate = entitlements.today()): String {
        val band = if (linked(context).learningGrade <= 4) "G3_4" else "G5_6"
        return "gradeBand=$band&date=$date"
    }

    /** 학습 완료 확인: 시도 상세가 `COMPLETED`면 그 미션 ID. 조회 실패·다른 상태는 null(적립하지 않음) */
    private fun completedMission(attempt: UUID): UUID? = try {
        val response = client.exchange("GET", "/attempts/$attempt")
        val node = if (response.status == 200) json.readTree(response.body) else null
        if (node?.path("status")?.asText() != "COMPLETED") null else UUID.fromString(node.path("mission").path("id").asText())
    } catch (error: Exception) {
        log.warn("completed attempt lookup failed; mission point not earned: attempt={}: {}", attempt, error.toString())
        null
    }

    private fun errorCode(response: HttpExchangeResult) = if (response.status != 409) null else
        try { json.readTree(response.body).path("code").asText(null) } catch (_: Exception) { null }

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

    private companion object { val log = LoggerFactory.getLogger(LearningProxyService::class.java) }
}
