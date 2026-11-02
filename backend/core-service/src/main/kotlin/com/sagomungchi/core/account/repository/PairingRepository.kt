package com.sagomungchi.core.account.repository

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.account.domain.StudentPairing
import org.springframework.data.redis.core.StringRedisTemplate
import org.springframework.data.redis.core.script.DefaultRedisScript
import org.springframework.stereotype.Repository
import java.time.Duration

@Repository
class PairingRepository(private val redis: StringRedisTemplate, private val json: ObjectMapper) {
    fun put(hash: String, pairing: StudentPairing): Boolean =
        redis.opsForValue().setIfAbsent("student-device:pairing:$hash",json.writeValueAsString(pairing),Duration.ofMinutes(10))==true
    fun consume(hash: String): StudentPairing? {
        val raw=redis.execute(CONSUME,listOf("student-device:pairing:$hash")) ?: return null
        return json.readValue(raw,StudentPairing::class.java)
    }
    fun attempt(key: String): Long = requireNotNull(redis.execute(ATTEMPT,listOf("student-device:attempt:$key")))
    private companion object {
        val CONSUME=DefaultRedisScript("local v=redis.call('GET',KEYS[1]); if v then redis.call('DEL',KEYS[1]) end; return v",String::class.java)
        val ATTEMPT=DefaultRedisScript("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],600) end; return n",Long::class.java)
    }
}
