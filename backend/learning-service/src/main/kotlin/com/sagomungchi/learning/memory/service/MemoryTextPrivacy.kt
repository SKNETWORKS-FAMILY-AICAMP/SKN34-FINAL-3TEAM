package com.sagomungchi.learning.memory.service

import com.sagomungchi.learning.memory.client.StudentProfileClient
import org.springframework.stereotype.Component
import java.util.UUID

/** 닉네임을 확인하지 못하면 외부 AI로 전송하지 않는다. */
@Component
class MemoryTextPrivacy(private val profiles: StudentProfileClient) {
    fun nickname(studentId: UUID): String = profiles.nickname(studentId)
    fun mask(text: String,nickname: String): String =
        (if(nickname.isBlank()) text else text.replace(nickname,"[학생]"))
            .replace(UUID_PATTERN,"[식별자]").take(8000)
    companion object { private val UUID_PATTERN=Regex("(?i)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}") }
}
