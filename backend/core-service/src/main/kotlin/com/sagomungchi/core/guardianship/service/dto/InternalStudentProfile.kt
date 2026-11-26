package com.sagomungchi.core.guardianship.service.dto

import java.util.UUID

/**
 * Minimal internal response; do not expose the full repository profile.
 * [parentSharingEnabled] is always true since #1064 (GUARDIAN 1.2) and is kept only so an older report image still reads
 * originals after a revert; the follow-up issue removes it with the column.
 */
data class InternalStudentProfile(val studentId: UUID, val nickname: String, val grade: Int, val parentSharingEnabled: Boolean = true)
