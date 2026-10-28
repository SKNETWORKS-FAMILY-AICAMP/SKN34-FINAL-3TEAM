package com.sagomungchi.core.account.service

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.account.client.GoogleOAuthClient
import com.sagomungchi.core.account.config.AuthProperties
import com.sagomungchi.core.account.domain.*
import com.sagomungchi.core.account.repository.AuthRepository
import com.sagomungchi.core.account.repository.ReauthenticationRepository
import com.sagomungchi.core.guardianship.service.ChildAuthorizationService
import org.springframework.http.HttpStatus
import org.springframework.stereotype.Service
import org.springframework.transaction.PlatformTransactionManager
import org.springframework.transaction.support.TransactionTemplate
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.time.OffsetDateTime
import java.util.UUID

@Service
class ReauthenticationService(private val repository: ReauthenticationRepository,
 private val accounts: AccountManagementService, private val auth: AuthRepository,
 private val google: GoogleOAuthClient, private val tokens: TokenService,
 private val properties: AuthProperties, private val students: ChildAuthorizationService,
 manager: PlatformTransactionManager) {
 private val tx=TransactionTemplate(manager)
 data class Started(val challengeId: UUID, val authorizationUrl: String, val expiresAt: OffsetDateTime, val stateCookie: String)
 data class Issued(val reauthToken: String, val expiresAt: OffsetDateTime)
 fun start(identity: AuthenticatedAccount, purpose: ReauthPurpose, childId: UUID?, scope: String?): Started {
  if((purpose==ReauthPurpose.WITHDRAWAL && (childId!=null || scope!=null)) ||
   (purpose!=ReauthPurpose.WITHDRAWAL && childId==null) ||
   (purpose==ReauthPurpose.CHILD_DELETE && scope !in setOf("PROFILE","RECORDS")) ||
   (purpose!=ReauthPurpose.CHILD_DELETE && scope!=null))
   throw BusinessException(HttpStatus.BAD_REQUEST,"VALIDATION_FAILED","재인증 대상과 작업 범위를 확인해 주세요.")
  val id=UUID.randomUUID(); val state=tokens.randomToken(); val nonce="$id:${tokens.randomToken()}"; val verifier=tokens.randomToken()
  val url=google.reauthAuthorizationUrl(state,nonce,verifier)
  return requireNotNull(tx.execute {
   accounts.lock(identity)
   if(identity.account.subject.isNullOrBlank()) throw required()
   if(childId!=null) students.requireOwned(identity.account.id,childId,purpose!=ReauthPurpose.CHILD_DELETE)
   val expiry=minOf(now().plusMinutes(10),identity.session.expiresAt)
   repository.insert(ReauthChallenge(id,identity.account.id,identity.session.id,identity.session.version,purpose.name,
    childId,scope,tokens.hash(state),expiry,null,null))
   Started(id,url,expiry,tokens.oauthState(state,nonce,verifier))
  })
 }
 /** Google network calls finish before the database mutation transaction. */
 fun callback(code: String?, state: String?, error: String?, cookie: String?): UUID {
  if(code.isNullOrBlank() || state.isNullOrBlank() || error!=null || cookie.isNullOrBlank()) throw required()
  val claims=try { tokens.verify(cookie,"oauth") } catch(_: BusinessException) { throw required() }
  if(!tokens.same(state,claims.getClaimAsString("state"))) throw required()
  // State is random; only its hash is persisted. The callback cookie carries the bound challenge ID separately.
  val id=try { UUID.fromString(claims.getClaimAsString("nonce").substringBefore(":")) } catch(_: Exception) { throw required() }
  val challenge=repository.find(id) ?: throw required()
  if(challenge.stateHash!=tokens.hash(state) || !challenge.expiresAt.isAfter(now()) || challenge.verifiedAt!=null) throw required()
  val profile=google.exchangeReauth(code,claims.getClaimAsString("verifier"),claims.getClaimAsString("nonce"))
  tx.executeWithoutResult {
   val account=auth.account(challenge.userId) ?: throw required()
   val session=auth.session(challenge.sessionId) ?: throw required()
   accounts.lock(AuthenticatedAccount(account,session,emptySet(),emptySet()))
   val current=repository.find(id,true) ?: throw required()
   if(current.sessionVersion!=session.version || current.verifiedAt!=null || !current.expiresAt.isAfter(now()) || account.subject!=profile.subject) throw required()
   repository.verify(id,now())
   accounts.audit(account.id,"GOOGLE_REAUTHENTICATED",id)
  }
  return id
 }
 fun issue(identity: AuthenticatedAccount, id: UUID): Issued = requireNotNull(tx.execute {
  accounts.lock(identity)
  val c=repository.find(id,true) ?: throw required()
  checkBinding(c,identity)
  if(c.issuedAt!=null || !c.expiresAt.isAfter(now())) throw required()
  if(c.verifiedAt==null) throw BusinessException(HttpStatus.CONFLICT,"REAUTH_PENDING","Google 재인증을 먼저 완료해 주세요.")
  val token=tokens.randomToken(); val expiry=minOf(now().plus(properties.reauthTtl),identity.session.expiresAt)
  repository.issue(id,now()); repository.insertGrant(ReauthGrant(tokens.hash(token),id,expiry,null))
  Issued(token,expiry)
 })
 /** #58 PIN service consumes this in the same transaction as the actual PIN mutation. */
 @Transactional(propagation=Propagation.MANDATORY)
 fun consume(identity: AuthenticatedAccount, token: String?, purpose: ReauthPurpose, childId: UUID?=null, scope: String?=null) {
  accounts.lock(identity)
  if(token.isNullOrBlank() || token.length>128) throw required()
  val hash=tokens.hash(token); val grant=repository.grant(hash) ?: throw required()
  val c=repository.find(grant.challengeId) ?: throw required()
  checkBinding(c,identity)
  if(c.verifiedAt==null || c.issuedAt==null || c.purpose!=purpose.name || c.studentId!=childId || c.scope!=scope ||
   grant.usedAt!=null || !grant.expiresAt.isAfter(now()) || repository.consume(hash,now())!=1) throw required()
 }
 private fun checkBinding(c: ReauthChallenge, identity: AuthenticatedAccount) {
  if(c.userId!=identity.account.id || c.sessionId!=identity.session.id || c.sessionVersion!=identity.session.version) throw required()
 }
 private fun now()=AccountManagementService.now()
 private fun required()=BusinessException(HttpStatus.FORBIDDEN,"REAUTH_REQUIRED","해당 작업의 Google 재인증이 필요합니다.")
}
