package com.sagomungchi.core.account.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.domain.*
import com.sagomungchi.core.account.repository.AccountManagementRepository
import com.sagomungchi.core.guardianship.service.ChildManagementService
import com.sagomungchi.core.payment.service.WithdrawalEligibilityService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.util.UUID

@Service
class AccountWithdrawalService(private val accounts: AccountManagementService,
 private val repository: AccountManagementRepository, private val children: ChildManagementService,
 private val payment: WithdrawalEligibilityService, private val reauth: ReauthenticationService,
 private val tokens: TokenService, private val devices: StudentDeviceCleanupService) {
 data class State(val withdrawalRequestId: UUID, val status: String)
 data class Requested(val withdrawalRequestId: UUID, val status: String, val statusToken: String)
 @Transactional
 fun precheck(identity: AuthenticatedAccount): Any { accounts.lock(identity); return payment.check(identity.account.id) }
 @Transactional
 fun request(identity: AuthenticatedAccount, token: String?): Requested {
  accounts.lock(identity)
  payment.requireEligible(identity.account.id)
  reauth.consume(identity,token,ReauthPurpose.WITHDRAWAL)
  val id=UUID.randomUUID(); val receipt=tokens.randomToken(); val now=AccountManagementService.now()
  repository.request(id,identity.account.id,tokens.hash(receipt),now)
  repository.withdraw(identity.account.id,now); repository.revokeAll(identity.account.id,now)
  devices.revokeOwner(identity.account.id)
  children.deleteForWithdrawal(identity.account.id)
  if(!children.hasRemaining(identity.account.id)) accounts.completeWithdrawal(identity.account.id)
  accounts.audit(identity.account.id,"WITHDRAWAL_REQUESTED",id)
  return Requested(id,repository.latest(identity.account.id)!!.status,receipt)
 }
 fun status(identity: AuthenticatedAccount?, receipt: String?): State {
  val row=if(receipt!=null) {
   if(receipt.isBlank() || receipt.length>128) throw unauthorized()
   repository.receipt(tokens.hash(receipt)) ?: throw unauthorized()
  } else {
   if(identity==null || identity.session.role !in setOf("PARENT","ADMIN")) throw unauthorized()
   repository.latest(identity.account.id) ?: throw BusinessException(HttpStatus.NOT_FOUND,"NOT_FOUND","탈퇴 요청이 없습니다.")
  }
  return State(row.id,row.status)
 }
 private fun unauthorized()=BusinessException(HttpStatus.UNAUTHORIZED,"UNAUTHENTICATED","유효한 탈퇴 상태 조회 권한이 필요합니다.")
}
