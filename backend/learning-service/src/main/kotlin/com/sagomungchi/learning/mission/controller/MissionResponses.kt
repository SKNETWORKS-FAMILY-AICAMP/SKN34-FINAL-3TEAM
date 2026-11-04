package com.sagomungchi.learning.mission.controller

/** 목록 봉투 (api-spec 1.1) */
data class PageResponse<T>(
    val items: List<T>,
    val page: Int,
    val size: Int,
    val totalElements: Long,
)
