package com.sagomungchi.core._common.web.repository

import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.jdbc.datasource.SingleConnectionDataSource
import org.springframework.stereotype.Repository
import java.nio.ByteBuffer
import java.security.MessageDigest
import java.sql.Connection
import java.util.UUID
import javax.sql.DataSource

data class IdempotencyRecord(val endpoint: String, val requestHash: String, val status: Int?, val response: String?)

/** A session lock must stay on its owning connection, including when no transaction is open. */
class IdempotencyLease internal constructor(
    internal val connection: Connection, internal val lockId: Long, val key: UUID, val user: UUID,
) : AutoCloseable {
    internal val jdbc = JdbcTemplate(SingleConnectionDataSource(connection, true))
    override fun close() {
        try {
            jdbc.queryForObject("SELECT pg_advisory_unlock(?)", Boolean::class.java, lockId)
        } catch (ex: Exception) {
            // Never return a session with an unknown lock state to the pool.
            try { connection.abort { it.run() } } catch (abort: Exception) { ex.addSuppressed(abort) }
            throw ex
        } finally { connection.close() }
    }
}

@Repository
class IdempotencyRepository(private val dataSource: DataSource) {
    fun findUnexpired(key: UUID, user: UUID): IdempotencyRecord? = JdbcTemplate(dataSource).query("""
        SELECT endpoint,request_hash,response_status,response_body::text FROM idempotency_record
        WHERE idempotency_key=? AND user_id=? AND (expires_at IS NULL OR expires_at>clock_timestamp())
    """.trimIndent(), { rs, _ -> IdempotencyRecord(rs.getString(1), rs.getString(2), rs.getObject(3) as Int?, rs.getString(4)) }, key, user).singleOrNull()

    fun acquire(key: UUID, user: UUID): IdempotencyLease? {
        val connection = dataSource.connection
        try {
            check(connection.autoCommit) { "Idempotency lock requires auto-commit" }
            val hash = MessageDigest.getInstance("SHA-256").digest("$user:$key".toByteArray())
            val lease = IdempotencyLease(connection, ByteBuffer.wrap(hash).long, key, user)
            if (lease.jdbc.queryForObject("SELECT pg_try_advisory_lock(?)", Boolean::class.java, lease.lockId) == true)
                return lease
            connection.close()
            return null
        } catch (ex: Exception) { connection.close(); throw ex }
    }

    fun prepare(lease: IdempotencyLease, endpoint: String, hash: String): IdempotencyRecord {
        lease.jdbc.update("DELETE FROM idempotency_record WHERE idempotency_key=? AND user_id=? AND expires_at<=clock_timestamp()", lease.key, lease.user)
        lease.jdbc.update("""
            INSERT INTO idempotency_record(idempotency_key,user_id,endpoint,request_hash,created_at,expires_at)
            VALUES(?,?,?,?,clock_timestamp(),clock_timestamp()+interval '24 hours') ON CONFLICT DO NOTHING
        """.trimIndent(), lease.key, lease.user, endpoint, hash)
        return lease.jdbc.queryForObject("""
            SELECT endpoint,request_hash,response_status,response_body::text FROM idempotency_record
            WHERE idempotency_key=? AND user_id=?
        """.trimIndent(), { rs, _ -> IdempotencyRecord(rs.getString(1), rs.getString(2), rs.getObject(3) as Int?, rs.getString(4)) }, lease.key, lease.user)!!
    }

    fun complete(lease: IdempotencyLease, status: Int, response: String) {
        check(lease.jdbc.update("""
            UPDATE idempotency_record SET response_status=?,response_body=CAST(? AS jsonb)
            WHERE idempotency_key=? AND user_id=? AND response_status IS NULL
        """.trimIndent(), status, response, lease.key, lease.user) == 1) { "Idempotency result was not stored" }
    }

    fun deleteExpired(): Int = JdbcTemplate(dataSource)
        .update("DELETE FROM idempotency_record WHERE expires_at<=clock_timestamp()")
}
