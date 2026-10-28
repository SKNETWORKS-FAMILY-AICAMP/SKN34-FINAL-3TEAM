package com.sagomungchi.core.account.controller
import com.sagomungchi.core.account.domain.AuthenticatedAccount
import com.sagomungchi.core.account.service.AccountManagementService
import com.sagomungchi.core.account.service.AccountWithdrawalService
import jakarta.servlet.http.HttpServletRequest
import org.springframework.http.*
import org.springframework.web.bind.annotation.*

@RestController
class AccountManagementController(private val accounts: AccountManagementService, private val withdrawals: AccountWithdrawalService,
 private val cookies: AuthCookies) {
 data class NameRequest(val name: String)
 @PatchMapping("/api/v1/me")
 fun rename(@RequestBody body: NameRequest, request: HttpServletRequest)=ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(accounts.rename(identity(request),body.name))
 @GetMapping("/api/v1/me/withdrawal/precheck")
 fun precheck(request: HttpServletRequest)=ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(withdrawals.precheck(identity(request)))
 @PostMapping("/api/v1/me/withdrawal")
 fun withdraw(@RequestHeader(value="X-Reauth-Token",required=false) token: String?, request: HttpServletRequest)=
  ResponseEntity.status(HttpStatus.ACCEPTED).cacheControl(CacheControl.noStore()).header(HttpHeaders.SET_COOKIE,cookies.clearRefresh().toString())
   .body(withdrawals.request(identity(request),token))
 @GetMapping("/api/v1/me/withdrawal")
 fun status(@RequestHeader(value="X-Withdrawal-Status-Token",required=false) receipt: String?, request: HttpServletRequest)=
  ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(withdrawals.status(request.getAttribute(AuthController.IDENTITY) as? AuthenticatedAccount,receipt))
 private fun identity(request: HttpServletRequest)=request.getAttribute(AuthController.IDENTITY) as AuthenticatedAccount
}
