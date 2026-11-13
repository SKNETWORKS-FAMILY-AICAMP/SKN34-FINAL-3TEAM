package com.sagomungchi.learning.community.repository

import com.sagomungchi.learning.community.domain.CommunityPost
import com.sagomungchi.learning.community.domain.CommunityPostStatus
import com.sagomungchi.learning.community.domain.CommunityReaction
import com.sagomungchi.learning.community.domain.ReactionRow
import com.sagomungchi.learning.community.domain.SharedAnswerRow
import com.sagomungchi.learning.community.domain.VisibilityReason
import com.sagomungchi.learning.mission.domain.InputType
import com.fasterxml.jackson.databind.ObjectMapper
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.springframework.stereotype.Repository
import java.time.Instant
import java.util.UUID

data class SharedAnswerRecord(
    val postId: UUID,
    val studentId: UUID,
    val missionId: UUID,
    val missionTitle: String?,
    val status: CommunityPostStatus,
    val inputType: InputType,
    val plainText: String?,
    val contentJson: String,
    val createdAt: Instant,
)

@Mapper
interface CommunityMapper {
    fun findPost(@Param("id") id: UUID, @Param("lock") lock: Boolean): CommunityPost?
    fun findByStudentMission(@Param("studentId") studentId: UUID, @Param("missionId") missionId: UUID): CommunityPost?
    fun insertPost(post: CommunityPost): Int
    fun updateStatus(@Param("id") id: UUID, @Param("status") status: CommunityPostStatus,
                     @Param("errorReportId") errorReportId: UUID?, @Param("now") now: Instant): Int
    fun switchStudentPosts(@Param("studentId") studentId: UUID, @Param("from") from: CommunityPostStatus,
                           @Param("to") to: CommunityPostStatus, @Param("now") now: Instant): Int
    fun lockVisibility(@Param("studentId") studentId: UUID): Boolean?
    fun upsertVisibility(@Param("studentId") studentId: UUID, @Param("visible") visible: Boolean,
                         @Param("reason") reason: VisibilityReason, @Param("now") now: Instant): Int
    fun findVisibility(@Param("studentId") studentId: UUID): Boolean?
    fun missionPosts(@Param("missionId") missionId: UUID, @Param("viewer") viewer: UUID, @Param("seed") seed: String,
                     @Param("limit") limit: Int, @Param("offset") offset: Int): List<SharedAnswerRecord>
    fun studentPosts(@Param("studentId") studentId: UUID): List<SharedAnswerRecord>
    fun sharedAnswer(@Param("postId") postId: UUID): SharedAnswerRecord?
    fun reactionsOf(@Param("postIds") postIds: Collection<UUID>, @Param("studentId") studentId: UUID): List<ReactionRow>
    fun reactionCounts(@Param("postIds") postIds: Collection<UUID>): List<ReactionRow>
    fun insertReaction(@Param("id") id: UUID, @Param("postId") postId: UUID, @Param("studentId") studentId: UUID,
                       @Param("reaction") reaction: CommunityReaction, @Param("now") now: Instant): Int
    fun deleteReaction(@Param("postId") postId: UUID, @Param("studentId") studentId: UUID,
                       @Param("reaction") reaction: CommunityReaction): Int
    fun deleteReactionsOnPostsOf(@Param("studentId") studentId: UUID): Int
    fun deleteReactionsBy(@Param("studentId") studentId: UUID): Int
    fun deletePostsOf(@Param("studentId") studentId: UUID): Int
    fun deleteVisibility(@Param("studentId") studentId: UUID): Int
}

/** 커뮤니티 공유물·반응·공개 여부 (ERD 4.4). 트랜잭션은 시작하지 않음 */
@Repository
class CommunityRepository(private val mapper: CommunityMapper, private val objectMapper: ObjectMapper) {
    private fun decode(row: SharedAnswerRecord): SharedAnswerRow {
        val node = objectMapper.readTree(row.contentJson)
        val content: Map<String, Any?> = objectMapper.convertValue(node, objectMapper.typeFactory.constructMapType(Map::class.java, String::class.java, Any::class.java))
        return SharedAnswerRow(row.postId, row.studentId, row.missionId, row.missionTitle, row.status,
            row.inputType, row.plainText ?: node.path("text").asText(""), content, row.createdAt)
    }

    fun findPost(id: UUID, lock: Boolean = false): CommunityPost? = mapper.findPost(id, lock)

    fun findByStudentMission(studentId: UUID, missionId: UUID): CommunityPost? = mapper.findByStudentMission(studentId, missionId)

    /** 같은 학생·미션(또는 같은 시도)의 공유물이 이미 있으면 넣지 않고 false (UK, 동시 요청 포함) */
    fun insertIfAbsent(post: CommunityPost): Boolean = mapper.insertPost(post) == 1

    fun updateStatus(id: UUID, status: CommunityPostStatus, errorReportId: UUID?, now: Instant) {
        check(mapper.updateStatus(id, status, errorReportId, now) == 1) { "공유물 상태를 바꾸지 못함" }
    }

    /** 학생 공유물 중 from 상태만 to로. 바꾼 수 */
    fun switchStudentPosts(studentId: UUID, from: CommunityPostStatus, to: CommunityPostStatus, now: Instant): Int =
        mapper.switchStudentPosts(studentId, from, to, now)

    /** 공개 여부 저장. 같은 학생의 공개 전환을 줄 세우려고 행을 잠근 뒤 바꾼다 */
    fun saveVisibility(studentId: UUID, visible: Boolean, reason: VisibilityReason, now: Instant) {
        mapper.lockVisibility(studentId)
        check(mapper.upsertVisibility(studentId, visible, reason, now) == 1) { "공개 여부를 저장하지 못함" }
    }

    /** core가 마지막으로 알린 공개 여부. 알린 적이 없으면 null */
    fun findVisibility(studentId: UUID): Boolean? = mapper.findVisibility(studentId)

    fun missionPosts(missionId: UUID, viewer: UUID, seed: String, page: Int, size: Int): List<SharedAnswerRow> =
        mapper.missionPosts(missionId, viewer, seed, size, page * size).map(::decode)

    fun studentPosts(studentId: UUID): List<SharedAnswerRow> = mapper.studentPosts(studentId).map(::decode)

    fun sharedAnswer(postId: UUID): SharedAnswerRow? = mapper.sharedAnswer(postId)?.let(::decode)

    /** 학생이 각 공유물에 남긴 반응 */
    fun reactionsOf(postIds: Collection<UUID>, studentId: UUID): Map<UUID, List<CommunityReaction>> =
        if (postIds.isEmpty()) emptyMap()
        else mapper.reactionsOf(postIds, studentId).groupBy({ it.postId }, { it.reaction })

    /** 공유물별 반응 종류별 수 (작성자·학부모 조회만) */
    fun reactionCounts(postIds: Collection<UUID>): Map<UUID, Map<CommunityReaction, Int>> =
        if (postIds.isEmpty()) emptyMap()
        else mapper.reactionCounts(postIds).groupBy { it.postId }.mapValues { (_, rows) -> rows.associate { it.reaction to it.count } }

    /** 이미 있으면 false (멱등) */
    fun insertReaction(id: UUID, postId: UUID, studentId: UUID, reaction: CommunityReaction, now: Instant): Boolean =
        mapper.insertReaction(id, postId, studentId, reaction, now) == 1

    /** 없었으면 false (멱등) */
    fun deleteReaction(postId: UUID, studentId: UUID, reaction: CommunityReaction): Boolean =
        mapper.deleteReaction(postId, studentId, reaction) == 1

    /**
     * 학생 삭제 (P09, #386): 그 학생 공유물에 달린 반응 → 그 학생이 남긴 반응 → 공유물 → 공개 여부 순서.
     * 시도·답변보다 먼저 지워야 FK(NO ACTION)에 걸리지 않음. 호출한 쪽 트랜잭션 안에서만. 지운 공유물 수
     */
    fun deleteByStudent(studentId: UUID): Int {
        mapper.deleteReactionsOnPostsOf(studentId)
        mapper.deleteReactionsBy(studentId)
        val posts = mapper.deletePostsOf(studentId)
        mapper.deleteVisibility(studentId)
        return posts
    }
}
