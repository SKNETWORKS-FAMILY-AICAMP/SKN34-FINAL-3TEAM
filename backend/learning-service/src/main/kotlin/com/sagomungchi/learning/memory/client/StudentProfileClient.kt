package com.sagomungchi.learning.memory.client

import com.sagomungchi.learning._common.config.InternalRestClientFactory
import com.sagomungchi.learning._common.security.UserContext
import com.sagomungchi.learning._common.security.UserContextHolder
import org.springframework.stereotype.Component
import java.util.UUID

/** core 학생 프로필의 닉네임 조회 (SYSTEM 컨텍스트·대상 학생 범위). 원문·ID는 예외 메시지에 넣지 않음. */
@Component
class StudentProfileClient(factory: InternalRestClientFactory) {
    private val core=factory.create("core")
    fun nickname(studentId: UUID): String {
        val previous=UserContextHolder.currentOrNull()
        try {
            UserContextHolder.set(UserContext(null,"SYSTEM",setOf(studentId.toString()),previous?.traceparent))
            val profile=core.get().uri("/internal/students/{id}/profile",studentId)
                .retrieve().body(Map::class.java) ?: error("학생 프로필 확인 실패")
            return profile["nickname"] as? String ?: error("학생 닉네임 확인 실패")
        } finally {
            if(previous==null) UserContextHolder.clear()
            else UserContextHolder.set(previous)
        }
    }
}
