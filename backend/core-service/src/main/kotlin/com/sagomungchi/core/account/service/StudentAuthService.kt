package com.sagomungchi.core.account.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.config.StudentDeviceProperties
import com.sagomungchi.core.account.domain.*
import com.sagomungchi.core.account.repository.PairingRepository
import com.sagomungchi.core.account.repository.StudentDeviceRepository
import com.sagomungchi.core.guardianship.domain.LinkedStudent
import com.sagomungchi.core.guardianship.domain.PinAttempt
import com.sagomungchi.core.guardianship.service.ChildAuthorizationService
import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.sagomungchi.core.guardianship.service.StudentPinService
import org.springframework.dao.DataAccessException
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.PlatformTransactionManager
import org.springframework.transaction.support.TransactionTemplate
import java.security.SecureRandom
import java.time.OffsetDateTime
import java.util.UUID

@Service
class StudentAuthService(private val devices: StudentDeviceRepository, private val pairings: PairingRepository,
    private val accounts: AccountManagementService, private val accountAccess: AccountAccessService,
    private val children: ChildAuthorizationService, private val students: StudentAccessService,
    private val pins: StudentPinService, private val auth: AuthService, private val tokens: TokenService,
    private val properties: StudentDeviceProperties, manager: PlatformTransactionManager) {
    private val tx=TransactionTemplate(manager)
    private val random=SecureRandom()
    data class PairingIssued(val pairingCode: String,val expiresAt: OffsetDateTime)
    data class Profile(val childId: UUID,val nickname: String,val pinSet: Boolean,val pinLocked: Boolean)
    data class DeviceChild(val childId: UUID,val nickname: String)
    data class DeviceItem(val deviceId: UUID,val label: String,val children: List<DeviceChild>,val createdAt: OffsetDateTime,val lastUsedAt: OffsetDateTime?,val expiresAt: OffsetDateTime)
    data class Registered(val deviceId: UUID,val children: List<DeviceChild>,val credential: String,val expiresAt: OffsetDateTime)
    data class LoggedIn(val accessToken: String,val child: LinkedStudent)
    private data class LoginOutcome(val login: LoggedIn?,val attempt: PinAttempt?)

    fun pairing(identity: AuthenticatedAccount, ids: List<UUID>): PairingIssued {
        if(ids.isEmpty() || ids.size>3 || ids.distinct().size!=ids.size) throw validation()
        tx.executeWithoutResult { accounts.lock(identity); ids.forEach { current(identity.account.id,it) } }
        return redis {
            limit("parent:${tokens.hash(identity.account.id.toString())}")
            repeat(5) {
                val code=(1..8).map { ALPHABET[random.nextInt(ALPHABET.length)] }.joinToString("")
                if(pairings.put(tokens.hash(code),StudentPairing(identity.account.id,ids)))
                    return@redis PairingIssued(code,now().plusMinutes(10))
            }
            throw unavailable()
        }
    }
    fun register(code: String,label: String,ip: String): Registered {
        val clean=label.trim()
        if(clean.isBlank() || clean.length>80) throw validation()
        val pairing=redis {
            limit("ip:${tokens.hash(ip)}")
            if(!code.matches(Regex("[A-Z0-9]{8}"))) throw invalidPairing()
            pairings.consume(tokens.hash(code)) ?: throw invalidPairing()
        }
        return requireNotNull(tx.execute {
            owner(pairing.parentId)
            val profiles=pairing.childIds.map { current(pairing.parentId,it) }
            val credential=tokens.randomToken(); val now=now()
            val device=StudentDevice(UUID.randomUUID(),pairing.parentId,tokens.hash(credential),clean,now,now.plus(properties.ttl),null,null)
            devices.insert(device,pairing.childIds)
            accounts.audit(pairing.parentId,"STUDENT_DEVICE_REGISTERED",device.id)
            Registered(device.id,profiles.map { DeviceChild(it.id,it.nickname) },credential,device.expiresAt)
        })
    }
    fun profiles(raw: String?): List<Profile> = requireNotNull(tx.execute {
        val device=lockedDevice(raw)
        devices.children(device.id).map { id ->
            val child=current(device.parentUserId,id); val pin=pins.state(id)
            Profile(child.id,child.nickname,pin.pinSet,pin.pinLocked)
        }
    })
    fun login(raw: String?,childId: UUID,pin: String): LoggedIn {
        val result=requireNotNull(tx.execute {
            val device=lockedDevice(raw,childId)
            if(childId !in devices.children(device.id)) throw invalidDevice()
            val child=current(device.parentUserId,childId)
            val attempt=pins.attempt(childId,pin)
            if(!attempt.accepted) return@execute LoginOutcome(null,attempt)
            val issued=auth.issueDeviceStudent(device.parentUserId,childId)
            devices.touch(device.id,now())
            LoginOutcome(LoggedIn(issued.accessToken,child),null)
        })
        result.attempt?.let { throw StudentPinFailure(it.code!!,it.remainingAttempts) }
        return requireNotNull(result.login)
    }
    fun list(identity: AuthenticatedAccount): List<DeviceItem> = requireNotNull(tx.execute {
        accounts.lock(identity)
        val linked=students.linkedStudents(identity.account.id).associateBy { it.id }
        devices.list(identity.account.id).map { d -> DeviceItem(d.id,d.label,
            devices.children(d.id).mapNotNull { id -> linked[id]?.let { DeviceChild(it.id,it.nickname) } },d.createdAt,d.lastUsedAt,d.expiresAt) }
    })
    fun revoke(identity: AuthenticatedAccount,id: UUID) {
        tx.executeWithoutResult {
            accounts.lock(identity)
            val device=devices.find(id,true)
            if(device==null || device.parentUserId!=identity.account.id)
                throw BusinessException(HttpStatus.NOT_FOUND,"NOT_FOUND","등록 기기를 찾을 수 없습니다.")
            if(device.revokedAt==null) { devices.revoke(id,now()); accounts.audit(identity.account.id,"STUDENT_DEVICE_REVOKED",id) }
        }
    }
    private fun lockedDevice(raw: String?, child: UUID?=null): StudentDevice {
        if(raw.isNullOrBlank() || raw.length>128) throw invalidDevice()
        val first=devices.byHash(tokens.hash(raw)) ?: throw invalidDevice()
        if(!first.usable(now()) || (child!=null && child !in devices.children(first.id))) throw invalidDevice()
        // Serialize with withdrawal, consent and child mutation; reread after acquiring owner lock.
        owner(first.parentUserId)
        return devices.find(first.id,true)?.takeIf { it.usable(now()) } ?: throw invalidDevice()
    }
    private fun owner(id: UUID) {
        try { accountAccess.lockParent(id) } catch(ex: BusinessException) { throw childUnavailable() }
    }
    private fun current(parent: UUID,child: UUID): LinkedStudent {
        try { children.requireCurrent(parent,child); return students.requireLinked(parent,child) }
        catch(ex: BusinessException) { throw childUnavailable() }
    }
    private fun limit(key: String) { if(pairings.attempt(key)>properties.attemptLimit) throw BusinessException(HttpStatus.TOO_MANY_REQUESTS,"RATE_LIMITED","잠시 후 다시 시도해 주세요.") }
    private fun <T> redis(block: () -> T): T = try { block() } catch(ex: DataAccessException) { throw unavailable() }
    private fun now()=AccountManagementService.now()
    private fun invalidDevice()=BusinessException(HttpStatus.UNAUTHORIZED,"STUDENT_DEVICE_INVALID","기기를 다시 등록해 주세요.")
    private fun invalidPairing()=BusinessException(HttpStatus.BAD_REQUEST,"PAIRING_CODE_INVALID","등록 코드가 유효하지 않습니다.")
    private fun validation()=BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","입력값을 확인해 주세요.")
    private fun childUnavailable()=BusinessException(HttpStatus.FORBIDDEN,"CHILD_NOT_LINKED","보호자·자녀 연결과 동의를 확인해 주세요.")
    private fun unavailable()=BusinessException(HttpStatus.SERVICE_UNAVAILABLE,"STUDENT_AUTH_UNAVAILABLE","기기 등록 서비스를 사용할 수 없습니다.")
    private companion object { const val ALPHABET="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" }
}

class StudentPinFailure(code: String,val remainingAttempts: Int?) : BusinessException(
    when(code) { "STUDENT_PIN_LOCKED" -> HttpStatus.LOCKED; "STUDENT_PIN_NOT_SET" -> HttpStatus.CONFLICT; else -> HttpStatus.UNAUTHORIZED },
    code,"PIN을 확인하거나 보호자에게 재설정을 요청해 주세요.")
