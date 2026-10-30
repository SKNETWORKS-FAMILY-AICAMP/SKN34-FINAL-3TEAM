package com.sagomungchi.core.guardianship.service.dto

import java.util.UUID

/** Minimal internal response; do not expose the full repository profile. */
data class InternalStudentProfile(val studentId: UUID, val nickname: String)
