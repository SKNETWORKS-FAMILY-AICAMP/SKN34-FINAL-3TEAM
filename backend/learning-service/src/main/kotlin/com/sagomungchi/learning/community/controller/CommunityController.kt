package com.sagomungchi.learning.community.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.community.domain.CommunityPostStatus
import com.sagomungchi.learning.community.domain.CommunityReaction
import com.sagomungchi.learning.community.domain.VisibilityReason
import com.sagomungchi.learning.community.service.CommunityService
import com.sagomungchi.learning.community.service.MissionPostView
import com.sagomungchi.learning.community.service.PostDetailView
import com.sagomungchi.learning.community.service.StudentPostView
import com.sagomungchi.learning.community.service.VisibilityResult
import org.springframework.http.CacheControl
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.DeleteMapping
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.PutMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController
import java.util.UUID

/**
 * 커뮤니티 내부 API (api-spec 4.1, #386). core #388 CommunityClient가 부르는 계약 그대로:
 * 공유·공개 전환·검토·원문은 SYSTEM, 열람·반응은 STUDENT(본인), 본인·자녀 목록은 STUDENT·PARENT + 대상 학생 scope
 */
@RestController
class CommunityController(private val service: CommunityService) {
    @PostMapping("/internal/community/posts")
    fun share(@RequestBody request: ShareRequest): ResponseEntity<ShareResponse> {
        val studentId = request.studentId ?: invalid("studentId 필요")
        val attemptId = request.attemptId ?: invalid("attemptId 필요")
        system().requireStudent(studentId)
        val shared = service.share(studentId, attemptId)
        return ResponseEntity.status(if (shared.created) HttpStatus.CREATED else HttpStatus.OK)
            .body(ShareResponse(shared.postId, shared.created, shared.status))
    }

    @GetMapping("/internal/community/posts/{postId}")
    fun post(@PathVariable postId: UUID): ResponseEntity<PostDetailView> {
        system()
        return noStore(service.post(postId))
    }

    @GetMapping("/internal/community/missions/{missionId}/posts")
    fun missionPosts(
        @PathVariable missionId: UUID,
        @RequestParam viewerStudentId: UUID,
        @RequestParam seed: String,
        @RequestParam(defaultValue = "0") page: Int,
        @RequestParam(defaultValue = "20") size: Int,
    ): ResponseEntity<MissionPostPage> {
        self(viewerStudentId)
        if (seed.isEmpty() || seed.length > MAX_SEED || page < 0 || size !in 1..MAX_SIZE) invalid("seed 1~100자, page 0 이상, size 1~100")
        return noStore(MissionPostPage(service.missionPosts(missionId, viewerStudentId, seed, page, size), page, size))
    }

    @GetMapping("/internal/community/students/{studentId}/posts")
    fun studentPosts(@PathVariable studentId: UUID): ResponseEntity<StudentPostList> {
        val context = UserContextHolder.current()
        when (context.role) {
            UserContext.STUDENT_ROLE -> self(studentId)
            PARENT_ROLE -> context.requireStudent(studentId)
            else -> forbidden()
        }
        return noStore(StudentPostList(studentId, service.studentPosts(studentId)))
    }

    @PutMapping("/internal/community/posts/{postId}/reactions/{reaction}")
    fun react(@PathVariable postId: UUID, @PathVariable reaction: String, @RequestParam studentId: UUID): ReactionCreated {
        self(studentId)
        val result = service.react(postId, studentId, reaction(reaction))
        return ReactionCreated(result.postId, result.reaction, result.reactionId, result.changed)
    }

    @DeleteMapping("/internal/community/posts/{postId}/reactions/{reaction}")
    fun cancelReaction(@PathVariable postId: UUID, @PathVariable reaction: String, @RequestParam studentId: UUID): ReactionDeleted {
        self(studentId)
        val result = service.cancelReaction(postId, studentId, reaction(reaction))
        return ReactionDeleted(result.postId, result.reaction, result.reactionId, result.changed)
    }

    @PutMapping("/internal/students/{studentId}/community-visibility")
    fun visibility(@PathVariable studentId: UUID, @RequestBody request: VisibilityRequest): VisibilityResult {
        system().requireStudent(studentId)
        val visible = request.visible ?: invalid("visible 필요")
        val reason = VisibilityReason.entries.firstOrNull { it.name == request.reason } ?: invalid("reason은 SETTING·CONSENT·TRANSFER")
        return service.setVisibility(studentId, visible, reason)
    }

    @PutMapping("/internal/community/posts/{postId}/moderation")
    fun moderate(@PathVariable postId: UUID, @RequestBody request: ModerationRequest): ModerationResponse {
        system()
        val status = CommunityPostStatus.entries.firstOrNull { it.name == request.status } ?: invalid("status는 HIDDEN_REPORT·VISIBLE·REMOVED")
        val errorReportId = request.errorReportId ?: invalid("errorReportId 필요")
        return ModerationResponse(postId, service.moderate(postId, status, errorReportId))
    }

    private fun system(): UserContext = UserContextHolder.current().takeIf { it.role == SYSTEM_ROLE } ?: forbidden()

    /** 학생 본인 요청이고 대상 학생이 본인이어야 함 */
    private fun self(studentId: UUID) {
        if (UserContextHolder.current().requireSelfStudent() != studentId) forbidden()
    }

    private fun reaction(value: String): CommunityReaction =
        CommunityReaction.entries.firstOrNull { it.name == value } ?: invalid("reaction은 NEW_IDEA·CLEAR_REASON·DIFFERENT_VIEW·WANT_MORE")

    private fun <T> noStore(body: T): ResponseEntity<T> = ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(body)

    private fun invalid(detail: String): Nothing = throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "입력값 오류", detail)

    private fun forbidden(): Nothing = throw BusinessException(HttpStatus.FORBIDDEN, "FORBIDDEN", "커뮤니티 내부 호출 권한 없음")

    companion object {
        private const val SYSTEM_ROLE = "SYSTEM"
        private const val PARENT_ROLE = "PARENT"
        private const val MAX_SEED = 100
        private const val MAX_SIZE = 100
    }
}

data class ShareRequest(val studentId: UUID? = null, val attemptId: UUID? = null)
data class ShareResponse(val postId: UUID, val created: Boolean, val status: CommunityPostStatus)
data class MissionPostPage(val items: List<MissionPostView>, val page: Int, val size: Int)
data class StudentPostList(val studentId: UUID, val items: List<StudentPostView>)
data class VisibilityRequest(val visible: Boolean? = null, val reason: String? = null)
data class ModerationRequest(val status: String? = null, val errorReportId: UUID? = null)
data class ModerationResponse(val postId: UUID, val status: CommunityPostStatus)

data class ReactionCreated(val postId: UUID, val reaction: CommunityReaction, val reactionId: UUID, val created: Boolean)
data class ReactionDeleted(val postId: UUID, val reaction: CommunityReaction, val reactionId: UUID, val deleted: Boolean)
