package com.sagomungchi.learning.wordhelp.controller

import com.sagomungchi.learning._common.exception.BusinessException
import com.sagomungchi.learning._common.exception.Problems
import com.sagomungchi.learning._common.security.UserContextHolder
import com.sagomungchi.learning.wordhelp.domain.WordHelpResult
import com.sagomungchi.learning.wordhelp.service.WordHelpException
import com.sagomungchi.learning.wordhelp.service.WordHelpService
import jakarta.servlet.http.HttpServletRequest
import org.springframework.http.HttpStatus
import org.springframework.http.ProblemDetail
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController
import java.util.UUID

data class WordHelpRequest(val question: String? = null)

data class WordHelpResponse(
    val state: String,
    val headword: String?,
    val text: String,
    val example: String?,
    val senses: List<WordSenseResponse>,
) {
    companion object {
        fun from(result: WordHelpResult) = WordHelpResponse(
            result.state, result.headword, result.text, result.example,
            result.senses.map { WordSenseResponse(it.definition, it.source, it.attribution, it.sourceUrl, it.license) },
        )
    }
}

data class WordSenseResponse(
    val definition: String,
    val source: String,
    val attribution: String?,
    val sourceUrl: String?,
    val license: String?,
)

/** 낱말 물어보기 (api-spec 2.2.1·4.1, #599). 본문 `{question}` 1~100자, 정의 밖 칸은 400(Jackson 설정) */
@RestController
@RequestMapping("/internal")
class WordHelpController(private val service: WordHelpService) {
    @PostMapping("/attempts/{attemptId}/word-help")
    fun help(@PathVariable attemptId: UUID, @RequestBody body: WordHelpRequest): WordHelpResponse {
        UserContextHolder.current().requireSelfStudent()
        val question = body.question?.trim()
        if (question.isNullOrEmpty() || question.length > 100)
            throw BusinessException(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "물어볼 낱말을 1~100자로 적어 주세요")
        return WordHelpResponse.from(service.help(attemptId, question))
    }

    /** ai 장애: 코드·retryable을 그대로 (`{"code":"DICTIONARY_UNAVAILABLE","retryable":true}`) */
    @ExceptionHandler(WordHelpException::class)
    fun unavailable(error: WordHelpException, request: HttpServletRequest): ProblemDetail =
        Problems.of(HttpStatus.valueOf(error.status), error.code,
            if (error.code == "DICTIONARY_UNAVAILABLE") "사전 조회 실패" else "낱말 설명 처리 실패",
            "잠시 후 다시 물어봐 주세요.", request).apply { setProperty("retryable", error.retryable) }
}
