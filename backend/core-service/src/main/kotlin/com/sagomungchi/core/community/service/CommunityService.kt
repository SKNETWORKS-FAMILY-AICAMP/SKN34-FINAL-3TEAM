package com.sagomungchi.core.community.service

import com.fasterxml.jackson.databind.JsonNode
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.community.client.CommunityClient
import com.sagomungchi.core.community.domain.Community
import com.sagomungchi.core.community.domain.VisibilityReason
import com.sagomungchi.core.community.repository.CommunityRepository
import com.sagomungchi.core.guardianship.service.ChildAuthorizationService
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.PlatformTransactionManager
import org.springframework.transaction.support.TransactionTemplate
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.temporal.ChronoUnit
import java.util.UUID

/**
 * 커뮤니티 공개 설정·learning 공유물 프록시(FN-RET-01~03, P20). 학생 ID는 learning 응답에서 작성자 표시로 바꾼 뒤 지운다.
 * 공개 판정(설정 + 현재 보호자 COMMUNITY 동의)과 신고 숨김은 learning 상태와 별도로 core가 다시 걸러, 공개 전환 호출이 실패해도 비공개를 지킨다.
 */
@Service
class CommunityService(private val repository: CommunityRepository, private val client: CommunityClient,
    private val visibility: CommunityVisibilityService, private val authors: CommunityAuthorMapper,
    private val students: StudentLearningContextService, private val children: ChildAuthorizationService,
    manager: PlatformTransactionManager) {
    data class Settings(val enabled: Boolean, val consentGranted: Boolean, val updatedAt: OffsetDateTime?)
    private data class Actor(val user: UUID, val student: UUID)

    private val log = LoggerFactory.getLogger(javaClass)
    private val tx = TransactionTemplate(manager)

    fun settings(): Settings {
        val actor = student()
        val state = repository.state(actor.student) ?: unavailable()
        return Settings(state.enabled, state.consentGranted, state.updatedAt)
    }

    /** 켜기는 동의가 있어야 한다. 같은 값이어도 learning 공개 상태를 다시 맞춰 이전 반영 실패를 보충한다. */
    fun updateSettings(enabled: Boolean): Settings {
        val actor = student()
        val saved = tx.execute {
            val state = repository.state(actor.student, lock = true) ?: unavailable()
            if (enabled && !state.consentGranted) throw BusinessException(HttpStatus.CONFLICT, "COMMUNITY_CONSENT_REQUIRED",
                "학부모님의 커뮤니티 동의가 먼저 필요해요.")
            val updatedAt = if (state.enabled == enabled) state.updatedAt else now().also {
                if (repository.update(actor.student, enabled, it) != 1) unavailable()
            }
            visibility.sync(actor.student, VisibilityReason.SETTING)
            Settings(enabled, state.consentGranted, updatedAt)
        }!!
        return saved
    }

    /** 돌아보기 저장(학습 완료) 뒤 공유 요청. 실패는 학습 응답을 바꾸지 않는다. 반환값은 포인트 적립(#389) 근거. */
    fun shareCompleted(attemptId: UUID): CommunityClient.SharedPost? = try {
        val actor = student()
        if (repository.state(actor.student)?.visible != true) null else client.createPost(actor.student, attemptId)
    } catch (ex: Exception) {
        log.warn("community share failed attempt={}: {}", attemptId, ex.toString())
        null
    }

    fun missionPosts(missionId: UUID, seed: String, page: Int, size: Int): Map<String, Any?> {
        if (seed.length > 100 || page < 0 || size !in 1..100) invalid()
        val actor = student()
        val items = client.missionPosts(missionId, actor.student, actor.user, seed, page, size).path("items")
        if (!items.isArray) invalidResponse()
        val rows = items.map { item -> Triple(item, uuid(item.path("postId")), uuid(item.path("studentId"))) }
        val shown = authors.toAuthors(rows.map { it.third }.toSet())
        val hidden = repository.reportHidden(rows.map { it.second }.toSet())
        // 학생 ID는 여기서 버린다. 반응 수도 learning이 주더라도 내보내지 않는다(작성자·학부모만).
        val visible = rows.filter { (_, post, author) -> author != actor.student && post !in hidden && shown[author] != null }
            .map { (item, post, author) ->
                mapOf("postId" to post, "author" to shown.getValue(author), "answer" to item.get("answer"),
                    "myReactions" to reactions(item.path("myReactions")), "createdAt" to item.get("createdAt"))
            }
        return mapOf("items" to visible, "page" to page, "size" to size)
    }

    fun myPosts(): Map<String, Any?> {
        val actor = student()
        return mapOf("items" to ownPosts(actor.student, client.studentPosts(actor.student, "STUDENT", actor.user)))
    }

    fun childPosts(childId: UUID): Map<String, Any?> {
        val context = UserContextHolder.current()
        if (context.role != "PARENT" || context.userId == null) forbidden()
        context.requireStudent(childId.toString())
        val parent = UUID.fromString(context.userId)
        children.requireCurrent(parent, childId)
        return mapOf("items" to ownPosts(childId, client.studentPosts(childId, "PARENT", parent)))
    }

    /** 반응 남기기·취소. 생성 여부를 돌려준다(포인트 적립 근거, #389). */
    fun react(postId: UUID, reaction: String, on: Boolean): Boolean {
        if (reaction !in Community.REACTIONS) invalid()
        val actor = student()
        if (on && postId in repository.reportHidden(setOf(postId)))
            throw BusinessException(HttpStatus.NOT_FOUND, "COMMUNITY_POST_NOT_FOUND", "볼 수 없는 공유물입니다.")
        return client.react(postId, actor.student, actor.user, reaction, on)
    }

    /** 내 공유물·자녀 공유물. core가 아는 비공개(설정·동의·신고)를 상태에 덮어써 learning 반영 지연을 숨기지 않는다. */
    private fun ownPosts(studentId: UUID, body: JsonNode): List<Map<String, Any?>> {
        val items = body.path("items")
        if (!items.isArray) invalidResponse()
        val visible = repository.state(studentId)?.visible == true
        val hidden = repository.reportHidden(items.map { uuid(it.path("postId")) }.toSet())
        return items.map { item ->
            val post = uuid(item.path("postId"))
            val reported = item.path("status").asText()
            if (reported !in Community.POST_STATUSES) invalidResponse()
            val status = when {
                reported == "REMOVED" -> reported
                post in hidden -> "HIDDEN_REPORT"
                reported == "VISIBLE" && !visible -> "HIDDEN_SETTING"
                else -> reported
            }
            val counts = item.path("reactions")
            mapOf("postId" to post, "missionId" to item.get("missionId"), "missionTitle" to item.get("missionTitle"),
                "answer" to item.get("answer"), "status" to status,
                "reactions" to Community.REACTIONS.associateWith { counts.path(it).asInt(0) }, "createdAt" to item.get("createdAt"))
        }
    }

    private fun reactions(node: JsonNode) = if (node.isArray) node.map { it.asText() }.filter { it in Community.REACTIONS } else emptyList()

    private fun student(): Actor {
        val context = UserContextHolder.currentOrNull()
        if (context?.role != "STUDENT" || context.userId == null || context.studentScope.size != 1) forbidden()
        val actor = Actor(UUID.fromString(context.userId), UUID.fromString(context.studentScope.single()))
        students.requireLinked(actor.user, actor.student)
        return actor
    }

    private fun uuid(node: JsonNode): UUID = try { UUID.fromString(node.asText()) } catch (_: IllegalArgumentException) { invalidResponse() }
    private fun now() = OffsetDateTime.now(ZoneOffset.UTC).truncatedTo(ChronoUnit.MICROS)
    private fun forbidden(): Nothing = throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 학생 세션이 필요합니다.")
    private fun unavailable(): Nothing = throw BusinessException(HttpStatus.CONFLICT, "STUDENT_UNAVAILABLE", "학생 상태를 다시 확인해 주세요.")
    private fun invalid(): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "입력값을 확인해 주세요.")
    private fun invalidResponse(): Nothing = throw BusinessException(HttpStatus.BAD_GATEWAY, "COMMUNITY_INVALID_RESPONSE", "커뮤니티 응답 계약이 올바르지 않습니다.")
}
