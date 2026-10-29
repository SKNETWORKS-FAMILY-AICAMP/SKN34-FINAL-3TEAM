package com.sagomungchi.core.payment.service
import com.sagomungchi.core.payment.repository.WithdrawalEligibilityRepository
import com.sagomungchi.core._common.exception.BusinessException
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import java.util.UUID

data class WithdrawalEligibility(val canWithdraw: Boolean, val activeSubscriptions: Int, val unresolvedRefunds: Int, val retainedTransactionsYears: Int=5, val pendingPayments: Int=0)
@Service
class WithdrawalEligibilityService(private val repository: WithdrawalEligibilityRepository) {
 fun check(user: UUID): WithdrawalEligibility {
  val subscriptions=repository.subscriptions(user); val refunds=repository.refunds(user)
  val pending=repository.pendingPayments(user)
  return WithdrawalEligibility(subscriptions==0 && refunds==0 && pending==0,subscriptions,refunds,pendingPayments=pending)
 }
 fun requireEligible(user: UUID) {
  if(!check(user).canWithdraw) throw BusinessException(HttpStatus.CONFLICT,"WITHDRAWAL_BLOCKED","진행 중 구독 또는 미처리 환불을 먼저 처리해 주세요.")
 }
}
