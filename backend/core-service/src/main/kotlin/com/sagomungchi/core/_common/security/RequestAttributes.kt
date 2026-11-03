package com.sagomungchi.core._common.security

/** 요청 속성 이름 (아키텍처 2.2: 기능은 다른 기능의 controller를 참조하지 않음, #251). 헤더 이름은 UserContext */
object RequestAttributes {
    /** PublicAuthFilter가 넣는 인증된 계정(AuthenticatedAccount). 공개 API 컨트롤러가 읽음 */
    const val IDENTITY = "sagomungchi.identity"
}
