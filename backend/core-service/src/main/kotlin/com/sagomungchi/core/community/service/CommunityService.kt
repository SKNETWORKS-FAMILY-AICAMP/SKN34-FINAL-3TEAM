package com.sagomungchi.core.community.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.community.client.CommunityClient
import com.sagomungchi.core.community.domain.Community
import com.sagomungchi.core.community.domain.VisibilityReason
import com.sagomungchi.core.community.repository.CommunityRepository
import com.sagomungchi.core.guardianship.service.ChildAuthorizationService
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import com.sagomungchi.core.reward.service.ParticipationRewardService
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
    private val rewards: ParticipationRewardService, manager: PlatformTransactionManager) {
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

    /** 돌아보기 저장(학습 완료) 뒤 공유 요청. 실패는 학습 응답을 바꾸지 않는다. 반환값으로 호출자가 공유 포인트를 적립한다(#389). */
    fun shareCompleted(attemptId: UUID): CommunityClient.SharedPost? = try {
        val actor = student()
        if (repository.state(actor.student)?.visible != true) null else client.createPost(actor.student, attemptId)
    } catch (ex: Exception) {
        log.warn("community share failed attempt={}: {}", attemptId, ex.toString())
        null
    }

    fun missionPosts(missionId: UUID, seed: String, page: Int, size: Int): Map<String, Any?> {
        if (seed.length !in 1..100 || page < 0 || size !in 1..100) invalid()
        val actor = student()
        val rows = client.missionPosts(missionId, actor.student, actor.user, seed, page, size)
        val shown = authors.toAuthors(rows.map { it.studentId }.toSet())
        val hidden = repository.reportHidden(rows.map { it.postId }.toSet())
        // 학생 ID는 여기서 버린다. 반응 수도 learning이 주더라도 내보내지 않는다(작성자·학부모만).
        val visible = rows.filter { it.studentId != actor.student && it.postId !in hidden && shown[it.studentId] != null }
            .map { post ->
                mapOf("postId" to post.postId, "author" to shown.getValue(post.studentId), "answer" to post.answer,
                    "myReactions" to post.myReactions, "createdAt" to post.createdAt)
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

    /**
     * 반응 남기기·취소. 생성 여부를 돌려준다. 남기기가 성공하면 반응 포인트를 적립한다(#389). 사건 키가 `postId:reaction`이라
     * 이미 있던 반응(`created:false`)을 다시 보내도 중복 적립은 없고, 앞선 적립 저장 실패만 보충된다. 적립 실패는 응답을 바꾸지 않는다.
     */
    fun react(postId: UUID, reaction: String, on: Boolean): Boolean {
        if (reaction !in Community.REACTIONS) invalid()
        val actor = student()
        if (on && postId in repository.reportHidden(setOf(postId)))
            throw BusinessException(HttpStatus.NOT_FOUND, "COMMUNITY_POST_NOT_FOUND", "볼 수 없는 공유물입니다.")
        val created = client.react(postId, actor.student, actor.user, reaction, on)
        if (on) rewards.reactionGiven(actor.student, postId, reaction)
        return created
    }

    /** 내 공유물·자녀 공유물. core가 아는 비공개(설정·동의·신고)를 상태에 덮어써 learning 반영 지연을 숨기지 않는다. */
    private fun ownPosts(studentId: UUID, posts: List<CommunityClient.StudentPost>): List<Map<String, Any?>> {
        val visible = repository.state(studentId)?.visible == true
        val hidden = repository.reportHidden(posts.map { it.postId }.toSet())
        return posts.map { post ->
            val status = when {
                post.status == "REMOVED" -> post.status
                post.postId in hidden -> "HIDDEN_REPORT"
                post.status == "VISIBLE" && !visible -> "HIDDEN_SETTING"
                else -> post.status
            }
            mapOf("postId" to post.postId, "missionId" to post.missionId, "missionTitle" to post.missionTitle,
                "answer" to post.answer, "status" to status, "reactions" to post.reactions, "createdAt" to post.createdAt)
        }
    }

    private fun student(): Actor {
        val context = UserContextHolder.currentOrNull()
        if (context?.role != "STUDENT" || context.userId == null || context.studentScope.size != 1) forbidden()
        val actor = Actor(UUID.fromString(context.userId), UUID.fromString(context.studentScope.single()))
        students.requireLinked(actor.user, actor.student)
        return actor
    }

    private fun now() = OffsetDateTime.now(ZoneOffset.UTC).truncatedTo(ChronoUnit.MICROS)
    private fun forbidden(): Nothing = throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "검증된 학생 세션이 필요합니다.")
    private fun unavailable(): Nothing = throw BusinessException(HttpStatus.CONFLICT, "STUDENT_UNAVAILABLE", "학생 상태를 다시 확인해 주세요.")
    private fun invalid(): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "입력값을 확인해 주세요.")
}
