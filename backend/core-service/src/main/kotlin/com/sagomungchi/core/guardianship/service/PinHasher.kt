package com.sagomungchi.core.guardianship.service

import org.springframework.stereotype.Component
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

/** Salted, deliberately expensive PIN verifier; never log inputs or encoded hashes. */
@Component
class PinHasher {
    private val random = SecureRandom()
    fun hash(pin: String): String {
        val salt=ByteArray(16).also(random::nextBytes)
        return listOf("pbkdf2-sha256",ITERATIONS.toString(),encode(salt),encode(derive(pin,salt))).joinToString("$")
    }
    fun matches(pin: String, encoded: String): Boolean {
        val parts=encoded.split('$')
        check(parts.size==4 && parts[0]=="pbkdf2-sha256" && parts[1]==ITERATIONS.toString()) { "Unsupported PIN hash format" }
        return MessageDigest.isEqual(derive(pin,Base64.getDecoder().decode(parts[2])),Base64.getDecoder().decode(parts[3]))
    }
    private fun derive(pin: String, salt: ByteArray): ByteArray {
        val spec=PBEKeySpec(pin.toCharArray(),salt,ITERATIONS,256)
        return try { SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).encoded } finally { spec.clearPassword() }
    }
    private fun encode(bytes: ByteArray)=Base64.getEncoder().encodeToString(bytes)
    private companion object { const val ITERATIONS=600_000 }
}
