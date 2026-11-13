package com.sagomungchi.learning.judgment.repository

import org.junit.jupiter.api.Test
import kotlin.test.assertEquals

class M2NoticeCodesTypeHandlerTest {
    private val handler = M2NoticeCodesTypeHandler()
    @Test
    fun `JSON 경계에서 문자열만 읽고 잘못된 모양과 SQL null은 빈 목록`() {
        assertEquals(listOf("SHORT_ANSWER", "UNKNOWN"), handler.decode("""["SHORT_ANSWER",5,null,{},"UNKNOWN"]"""))
        for (json in listOf(null, "null", "invalid", "5", "{}", "[]")) assertEquals(emptyList(), handler.decode(json))
    }
}
