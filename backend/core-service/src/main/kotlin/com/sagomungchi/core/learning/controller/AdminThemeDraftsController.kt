package com.sagomungchi.core.learning.controller
import com.sagomungchi.core.learning.service.AdminLearningService
import com.sagomungchi.core._common.web.operationPage
import com.sagomungchi.core._common.web.invalidOperations
import com.sagomungchi.core._common.web.HttpExchangeResult
import org.springframework.http.HttpHeaders
import org.springframework.http.HttpStatusCode
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.time.DayOfWeek
import java.time.LocalDate
import java.util.UUID

/**
 * 테마 초안 공개 경로 (#439, api-spec 2.8, 에픽 #436). learning `/internal/admin/theme-drafts…`(#438)로
 * 미션 초안과 같은 방식(CONTENT, ADMIN + X-User-Id + 빈 학생 범위)으로 넘김. 요청 본문 값 검사·상태 전이는 learning이 하고 오류 코드를 그대로 전달.
 */
@RestController
@RequestMapping("/api/v1/admin/theme-drafts")
class AdminThemeDraftsController(private val service: AdminLearningService) {
    @PostMapping fun request(@RequestBody body: ByteArray)=service.themeDrafts("POST",body=body).themeDraftHttp()
    @GetMapping
    fun list(@ModelAttribute filter: ListFilter) =
        service.themeDrafts("GET", query = filter.query()).themeDraftHttp()

    @GetMapping("/review-list")
    fun reviewList(@ModelAttribute filter: ListFilter, @RequestParam(required = false) stage: String?,
                   @RequestParam(required = false) week: LocalDate?): ResponseEntity<ByteArray> {
        if (stage != null && stage !in REVIEW_STAGES) invalidOperations()
        if (week != null && week.dayOfWeek != DayOfWeek.MONDAY) invalidOperations()
        return service.themeDrafts("GET", action = "review-list", query = filter.query(stage, week)).themeDraftHttp()
    }

    data class ListFilter(val status: String? = null, val source: String? = null, val grade: String? = null,
                          val weekStart: LocalDate? = null, val hideDiscarded: Boolean? = null,
                          val comparisonPending: Boolean? = null, val page: Int = 0, val size: Int = 20) {
        fun query(stage: String? = null, week: LocalDate? = null): String {
            operationPage(page, size)
            if (status != null && status !in DRAFT_STATUSES) invalidOperations()
            if (source != null && source !in DRAFT_SOURCES) invalidOperations()
            if (grade != null && grade !in setOf("G3", "G4", "G5", "G6")) invalidOperations()
            if (weekStart != null && weekStart.dayOfWeek != DayOfWeek.MONDAY) invalidOperations()
            return mapOf("page" to page, "size" to size, "status" to status, "source" to source, "grade" to grade,
                "weekStart" to weekStart, "hideDiscarded" to hideDiscarded, "comparisonPending" to comparisonPending,
                "stage" to stage, "week" to week).filterValues { it != null }.entries.joinToString("&") {
                "${it.key}=${URLEncoder.encode(it.value.toString(), StandardCharsets.UTF_8)}"
            }
        }
    }
    @GetMapping("/{draftId}") fun detail(@PathVariable draftId: UUID)=service.themeDrafts("GET",draftId).themeDraftHttp()
    @PostMapping("/{draftId}/adopt") fun adopt(@PathVariable draftId: UUID,@RequestBody body: ByteArray)=service.themeDrafts("POST",draftId,"adopt",body=body).themeDraftHttp()
    @PostMapping("/{draftId}/discard") fun discard(@PathVariable draftId: UUID,@RequestBody body: ByteArray)=service.themeDrafts("POST",draftId,"discard",body=body).themeDraftHttp()
    @PostMapping("/{draftId}/regenerate") fun regenerate(@PathVariable draftId: UUID,@RequestBody body: ByteArray)=service.themeDrafts("POST",draftId,"regenerate",body=body).themeDraftHttp()

    @GetMapping("/{draftId}/scenes/{scene}/versions")
    fun versions(@PathVariable draftId: UUID, @PathVariable scene: ReviewScene) =
        service.sceneVersions("GET", draftId, scene.name).themeDraftHttp()

    @PutMapping("/{draftId}/scenes/{scene}/versions/selection")
    fun choose(@PathVariable draftId: UUID, @PathVariable scene: ReviewScene, @RequestBody body: ByteArray) =
        service.sceneVersions("PUT", draftId, scene.name, body = body).themeDraftHttp()

    @PatchMapping("/{draftId}/scenes/{scene}/versions/{versionId}")
    fun annotate(@PathVariable draftId: UUID, @PathVariable scene: ReviewScene, @PathVariable versionId: UUID, @RequestBody body: ByteArray) =
        service.sceneVersions("PATCH", draftId, scene.name, versionId, body).themeDraftHttp()

    enum class ReviewScene { INTRO, MON, TUE, WED, THU, FRI, OUTRO }

    private companion object {
        val DRAFT_STATUSES=setOf("GENERATING","READY","CHECK_FAILED","FAILED","ADOPTED","DISCARDED")
        val DRAFT_SOURCES=setOf("AUTO","ADMIN")
        val REVIEW_STAGES = setOf("review", "pair", "adopted", "closed", "ready", "published", "discarded", "generating", "check_failed", "failed")
    }
}

private fun HttpExchangeResult.themeDraftHttp()=ResponseEntity(body,HttpHeaders().also { h -> headers.forEach { (n,v) -> h[n]=v } },HttpStatusCode.valueOf(status))
