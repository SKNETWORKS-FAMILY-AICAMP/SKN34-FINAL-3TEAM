package com.sagomungchi.learning.attempt.domain

import com.sagomungchi.learning.judgment.domain.ProcessStatus
import com.sagomungchi.learning.judgment.domain.TimelineAnswer

/** 마무리 조건 (class-diagram 4.1, P04): 시도 안에 판정 처리 완료(DONE)가 1회 이상. 결과는 보지 않음(보류 포함) */
object FinishPolicy {
    fun canFinish(timeline: List<TimelineAnswer>): Boolean = timeline.any { it.processStatus == ProcessStatus.DONE }
}
