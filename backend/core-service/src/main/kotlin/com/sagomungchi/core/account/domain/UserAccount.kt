package com.sagomungchi.core.account.domain

import java.time.Instant
import java.util.UUID

/** Persistence example only; registration/authentication policies belong to the account service. */
data class UserAccount(
    val id: UUID,
    val role: String,
    val loginId: String,
    val passwordHash: String,
    val displayName: String?,
    val status: String,
    val isDemo: Boolean,
    val createdAt: Instant,
    val updatedAt: Instant,
    val withdrawnAt: Instant?,
)
