package com.sagomungchi.core.guardianship.domain

import java.time.OffsetDateTime

/**
 * 학생 화면 꾸미기 설정 (api-spec 3.12, #234). 값 목록은 웹 `domain/studentLook.ts`의 ThemeId·CompanionId와 같고
 * V23 CHECK와도 맞춘다. 숫자 레벨·보상·잠금 없이 언제든 바꾼다.
 */
data class StudentLook(val theme: String, val companion: String, val updatedAt: OffsetDateTime?) {
    companion object {
        val THEMES = setOf("lake", "forest", "factory", "space", "sea")
        val COMPANIONS = setOf("mungchi", "tori", "mongdol", "kongi", "monggeul")
        val DEFAULT = StudentLook("lake", "mungchi", null)
    }
}
