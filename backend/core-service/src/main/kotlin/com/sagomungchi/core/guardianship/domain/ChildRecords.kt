package com.sagomungchi.core.guardianship.domain

data class ChildRecords(val hasRecords: Boolean?, val recordState: String)
data class ChildListItem(val id: java.util.UUID, val nickname: String, val grade: Int, val birthYear: Int,
    val guardianConsentRequired: Boolean, val hasRecords: Boolean?, val recordState: String)
