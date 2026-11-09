package com.sagomungchi.learning.community.service

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning.answer.domain.AnswerContent
import com.sagomungchi.learning.answer.domain.ExpressionPolicy
import com.sagomungchi.learning.attempt.domain.AttemptStatus
import com.sagomungchi.learning.attempt.service.AttemptService
import com.sagomungchi.learning.community.domain.CommunityPost
import com.sagomungchi.learning.community.domain.CommunityPostStatus
import com.sagomungchi.learning.community.domain.CommunityReaction
import com.sagomungchi.learning.community.domain.CommunityRules
import com.sagomungchi.learning.community.domain.SharedAnswerRow
import com.sagomungchi.learning.community.domain.VisibilityReason
import com.sagomungchi.learning.community.repository.CommunityRepository
import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID

/** 공유 결과. created는 이번 요청으로 새로 만들었는지(core 포인트 적립 근거, #389) */
data class SharedPost(val postId: UUID, val created: Boolean, val status: CommunityPostStatus)

/** 공유물에 보이는 답변: 입력 틀 칸 이름을 붙인 원문(text)과 입력 방식별 내용(content) */
data class SharedAnswer(val inputType: String, val text: String, val content: JsonNode)

data class MissionPostView(val postId: UUID, val studentId: UUID, val answer: SharedAnswer,
    val myReactions: List<CommunityReaction>, val createdAt: Instant)

data class StudentPostView(val postId: UUID, val missionId: UUID, val missionTitle: String?, val answer: SharedAnswer,
    val status: CommunityPostStatus, val reactions: Map<CommunityReaction, Int>, val createdAt: Instant)

data class PostDetailView(val postId: UUID, val studentId: UUID, val missionId: UUID, val status: CommunityPostStatus,
    val answer: SharedAnswer, val createdAt: Instant)

/** 반응 결과. reactionId는 같은 학생·공유물·반응이면 늘 같음(core 사건 키, #389). created·deleted는 이번 요청으로 바뀌었는지 */
data class ReactionResult(val postId: UUID, val reaction: CommunityReaction, val reactionId: UUID, val changed: Boolean)

data class VisibilityResult(val studentId: UUID, val visible: Boolean, val changed: Int)

/**
 * 커뮤니티 공유물·반응·열람 검사 (P20, FN-RET-02~04, api-spec 4.1). 공개 설정·동의·신고·작성자 별명은 core 몫(#388)이고
 * learning은 공유물·반응 저장과 "같은 미션을 학습 완료한 학생만" 검사를 맡는다. 학생 ID는 core가 별명으로 바꿔 내보낸다.
 */
@Service
class CommunityService(
    private val repository: CommunityRepository,
    private val attemptService: AttemptService,
    private val expressionPolicy: ExpressionPolicy,
    private val objectMapper: ObjectMapper,
) {
    private val log = LoggerFactory.getLogger(javaClass)

    /**
     * 학습 완료 시도 공유 (FN-RET-02). 학생·미션당 1개: 이미 있으면 그 공유물(created=false).
     * 처음 학습 완료한 시도가 아니면(다시 풀기)·완료 전·답변 없음·지금 표현 필터(#205)에 걸리면 409 COMMUNITY_NOT_SHAREABLE
     */
    @Transactional
    fun share(studentId: UUID, attemptId: UUID): SharedPost {
        val source = attemptService.communityShareSource(studentId, attemptId)
            ?: throw BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "학습 시도를 찾을 수 없습니다.")
        val attempt = source.attempt
        if (attempt.status != AttemptStatus.COMPLETED) notShareable("학습을 완료한 시도만 공유합니다.")
        repository.findByStudentMission(studentId, attempt.missionId)?.let { return SharedPost(it.id, false, it.status) }
        if (!source.firstCompleted) notShareable("다시 푼 시도는 공유하지 않습니다.")
        val answer = source.lastAnswer ?: notShareable("공유할 답변이 없습니다.")
        val content = objectMapper.convertValue(answer.content, AnswerContent::class.java)
        expressionPolicy.blockedCategory(content.writtenTexts(), source.mission)?.let { category ->
            // 걸린 말·원문은 남기지 않음 (NFR-SEC-05)
            log.info("커뮤니티 공유 표현 차단 attemptId={} category={}", attempt.id, category)
            notShareable("표현 확인을 통과한 답만 공유합니다.")
        }
        val now = now()
        val post = CommunityPost(UUID.randomUUID(), studentId, attempt.missionId, attempt.id, answer.answerId,
            CommunityRules.initialStatus(repository.findVisibility(studentId)), now, now, null)
        if (repository.insertIfAbsent(post)) return SharedPost(post.id, true, post.status)
        // 동시 요청이 먼저 만든 공유물 (UK 충돌)
        val existing = checkNotNull(repository.findByStudentMission(studentId, attempt.missionId)) { "공유물 충돌 후 조회 실패" }
        return SharedPost(existing.id, false, existing.status)
    }

    /**
     * 미션 공유물 무작위 목록 (FN-RET-02). 열람자가 그 미션을 학습 완료하지 않았으면 403 COMMUNITY_LOCKED.
     * VISIBLE만, 본인 공유물 제외, 반응 수 없음(작성자·학부모만), 같은 seed면 같은 순서
     */
    @Transactional(readOnly = true)
    fun missionPosts(missionId: UUID, viewer: UUID, seed: String, page: Int, size: Int): List<MissionPostView> {
        requireCompleted(viewer, missionId)
        val rows = repository.missionPosts(missionId, viewer, seed, page, size)
        val mine = repository.reactionsOf(rows.map { it.postId }, viewer)
        return rows.map { MissionPostView(it.postId, it.studentId, answer(it), mine[it.postId].orEmpty().sorted(), it.createdAt) }
    }

    /** 본인·자녀 공유물과 받은 반응 종류별 수 (FN-RET-03). 모든 상태 포함(상태는 core가 현재 공개 판정으로 덮어씀) */
    @Transactional(readOnly = true)
    fun studentPosts(studentId: UUID): List<StudentPostView> {
        val rows = repository.studentPosts(studentId)
        val counts = repository.reactionCounts(rows.map { it.postId })
        return rows.map { row ->
            val received = counts[row.postId].orEmpty()
            StudentPostView(row.postId, row.missionId, row.missionTitle, answer(row), row.status,
                CommunityReaction.entries.associateWith { received[it] ?: 0 }, row.createdAt)
        }
    }

    /** 신고 대상 확인·관리자 원문 열람 (core #388). 파기·없음 404 */
    @Transactional(readOnly = true)
    fun post(postId: UUID): PostDetailView {
        val row = repository.sharedAnswer(postId) ?: postNotFound()
        return PostDetailView(row.postId, row.studentId, row.missionId, row.status, answer(row), row.createdAt)
    }

    /**
     * 반응 남기기 (멱등, FN-RET-02). 공개(VISIBLE) 공유물만(아니면 404 COMMUNITY_POST_NOT_FOUND), 본인 글 409 COMMUNITY_OWN_POST,
     * 그 미션을 학습 완료하지 않았으면 403 COMMUNITY_LOCKED. 공유물 행을 잠가 신고 숨김·삭제와 차례로 처리
     */
    @Transactional
    fun react(postId: UUID, studentId: UUID, reaction: CommunityReaction): ReactionResult {
        val post = repository.findPost(postId, lock = true)?.takeIf { it.status == CommunityPostStatus.VISIBLE } ?: postNotFound()
        if (post.studentId == studentId) throw BusinessException(HttpStatus.CONFLICT, "COMMUNITY_OWN_POST", "내 공유물에는 반응할 수 없어요.")
        requireCompleted(studentId, post.missionId)
        val id = CommunityRules.reactionId(postId, studentId, reaction)
        return ReactionResult(postId, reaction, id, repository.insertReaction(id, postId, studentId, reaction, now()))
    }

    /** 반응 취소 (멱등). 숨긴 공유물이어도 내가 남긴 반응은 지울 수 있음. 공유물이 없으면 404 */
    @Transactional
    fun cancelReaction(postId: UUID, studentId: UUID, reaction: CommunityReaction): ReactionResult {
        repository.findPost(postId, lock = true) ?: postNotFound()
        return ReactionResult(postId, reaction, CommunityRules.reactionId(postId, studentId, reaction),
            repository.deleteReaction(postId, studentId, reaction))
    }

    /**
     * 공개 전환 (설정·동의·이관, state-diagram 3.6): 끄면 VISIBLE → HIDDEN_SETTING, 켜면 HIDDEN_SETTING만 VISIBLE로 복원.
     * 신고 숨김·계속 숨김은 그대로. 같은 값 반복은 멱등. 마지막 값은 신고 숨김을 풀 때·새 공유 때 쓰려고 저장
     */
    @Transactional
    fun setVisibility(studentId: UUID, visible: Boolean, reason: VisibilityReason): VisibilityResult {
        val now = now()
        repository.saveVisibility(studentId, visible, reason, now)
        val changed = if (visible) repository.switchStudentPosts(studentId, CommunityPostStatus.HIDDEN_SETTING, CommunityPostStatus.VISIBLE, now)
        else repository.switchStudentPosts(studentId, CommunityPostStatus.VISIBLE, CommunityPostStatus.HIDDEN_SETTING, now)
        return VisibilityResult(studentId, visible, changed)
    }

    /** 신고 검토 반영 (core #388, 멱등). 전이 규칙은 CommunityRules.moderate. 공유물이 없으면 404 */
    @Transactional
    fun moderate(postId: UUID, requested: CommunityPostStatus, errorReportId: UUID): CommunityPostStatus {
        if (requested !in CommunityRules.MODERATION_TARGETS) throw BusinessException(HttpStatus.BAD_REQUEST,
            "VALIDATION_FAILED", "입력값 오류", "status는 HIDDEN_REPORT·VISIBLE·REMOVED")
        val post = repository.findPost(postId, lock = true) ?: postNotFound()
        val next = CommunityRules.moderate(post.status, requested, repository.findVisibility(post.studentId) != false)
        // 같은 요청 반복은 바꾸지 않음. error_report_id는 상태를 마지막으로 바꾼 신고
        if (next != post.status) repository.updateStatus(postId, next, errorReportId, now())
        return next
    }

    /** 학생 삭제 (StudentDeletionService, P09): 그 학생 공유물(달린 반응 포함)·남긴 반응·공개 여부. 호출한 쪽 트랜잭션 안에서만 */
    @Transactional(propagation = Propagation.MANDATORY)
    fun deleteByStudent(studentId: UUID): Int = repository.deleteByStudent(studentId)

    private fun requireCompleted(studentId: UUID, missionId: UUID) {
        if (!attemptService.hasCompleted(studentId, missionId)) {
            throw BusinessException(HttpStatus.FORBIDDEN, "COMMUNITY_LOCKED", "커뮤니티 잠김", "이 미션을 마무리하면 친구들 생각을 볼 수 있어요.")
        }
    }

    private fun answer(row: SharedAnswerRow): SharedAnswer {
        val content = objectMapper.readTree(row.contentJson)
        return SharedAnswer(row.inputType.name, row.plainText ?: content.path("text").asText(""), content)
    }

    private fun notShareable(detail: String): Nothing =
        throw BusinessException(HttpStatus.CONFLICT, "COMMUNITY_NOT_SHAREABLE", "공유 대상 아님", detail)

    private fun postNotFound(): Nothing =
        throw BusinessException(HttpStatus.NOT_FOUND, "COMMUNITY_POST_NOT_FOUND", "공유물 없음", "볼 수 없는 공유물입니다.")

    private fun now() = Instant.now().truncatedTo(ChronoUnit.MICROS)
}
