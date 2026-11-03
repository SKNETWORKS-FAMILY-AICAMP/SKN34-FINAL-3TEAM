package com.sagomungchi.core.account.domain

import java.time.OffsetDateTime
import java.util.UUID

/** 학생 화면에서 잠긴 학부모 세션으로 돌아갈 때 쓰는 보호자 비밀번호 (FN-ACC-05). 해시만 저장한다. */
data class GuardianPassword(val userId: UUID, val passwordHash: String, val failedCount: Int,
    val lockedAt: OffsetDateTime?, val updatedAt: OffsetDateTime)
data class GuardianPasswordState(val set: Boolean, val locked: Boolean, val updatedAt: OffsetDateTime?)
