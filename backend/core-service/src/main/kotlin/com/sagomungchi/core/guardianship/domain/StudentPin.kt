package com.sagomungchi.core.guardianship.domain

import java.time.OffsetDateTime
import java.util.UUID

data class StudentPin(val id: UUID, val pinHash: String?, val pinFailedCount: Int,
    val pinLockedAt: OffsetDateTime?, val pinUpdatedAt: OffsetDateTime?)
data class PinState(val pinSet: Boolean, val pinLocked: Boolean)
data class PinAttempt(val accepted: Boolean, val code: String? = null, val remainingAttempts: Int? = null)

object PinRules {
    /** 연속 실패 이 횟수에 잠금 (api-spec 1.3 STUDENT_PIN_LOCKED "PIN 연속 5회 실패", #251: account 설정에서 guardianship으로) */
    const val FAILURE_LIMIT = 5

    fun valid(pin: String): Boolean = pin.matches(Regex("[0-9]{4,6}")) && pin.toSet().size > 1 &&
        !listOf(1, -1).any { step -> pin.zipWithNext().all { (a,b) -> b-a == step } }
}
