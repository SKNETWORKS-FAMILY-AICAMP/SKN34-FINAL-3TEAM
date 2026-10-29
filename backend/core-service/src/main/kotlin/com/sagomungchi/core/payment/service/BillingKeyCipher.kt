package com.sagomungchi.core.payment.service

import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.beans.factory.annotation.Value
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Component
import java.security.SecureRandom
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

@Component
class BillingKeyCipher(@Value("\${app.payment.billing-encryption-key:}") private val configured: String) {
    fun encrypt(value: String): String = protect {
        val iv=ByteArray(12).also { SecureRandom().nextBytes(it) }
        val cipher=Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE,key(),GCMParameterSpec(128,iv))
        Base64.getEncoder().encodeToString(iv+cipher.doFinal(value.toByteArray()))
    }
    fun decrypt(value: String): String = protect {
        val bytes=Base64.getDecoder().decode(value); require(bytes.size > 28)
        val cipher=Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE,key(),GCMParameterSpec(128,bytes.copyOfRange(0,12)))
        String(cipher.doFinal(bytes.copyOfRange(12,bytes.size)),Charsets.UTF_8)
    }
    private fun key()=SecretKeySpec(Base64.getDecoder().decode(configured).also { require(it.size == 32) },"AES")
    private fun <T> protect(block: () -> T): T = try { block() } catch (_: Exception) {
        throw BusinessException(HttpStatus.SERVICE_UNAVAILABLE,"PAYMENT_KEY_UNAVAILABLE","결제수단 보호 설정을 확인해 주세요.")
    }
}
