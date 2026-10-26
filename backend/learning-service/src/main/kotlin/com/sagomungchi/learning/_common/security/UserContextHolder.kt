package com.sagomungchi.learning._common.security

/**
 * 요청 처리 스레드의 사용자 컨텍스트. InternalAuthFilter가 설정·해제.
 */
object UserContextHolder {
    private val holder = ThreadLocal<UserContext>()

    fun current(): UserContext = checkNotNull(holder.get()) { "사용자 컨텍스트 없음" }

    fun currentOrNull(): UserContext? = holder.get()

    internal fun set(context: UserContext) = holder.set(context)

    internal fun clear() = holder.remove()
}
