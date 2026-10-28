package com.sagomungchi.core.guardianship

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.core._common.config.AppProperties
import com.sagomungchi.core._common.config.InternalRestClientFactory
import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.account.service.AccountAccessService
import com.sagomungchi.core.consent.service.ConsentAccessService
import com.sagomungchi.core.consent.service.ConsentService
import com.sagomungchi.core.guardianship.domain.LinkedStudent
import com.sagomungchi.core.guardianship.repository.StudentAccessRepository
import com.sagomungchi.core.guardianship.service.GuardianshipService
import com.sagomungchi.core.guardianship.service.StudentAccessService
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import com.sagomungchi.core.learning.LearningHttpStub
import com.sagomungchi.core.learning.client.LearningClient
import com.sagomungchi.core.learning.client.LearningHttpProperties
import com.sagomungchi.core.learning.client.LearningRecordClient
import com.sagomungchi.core.learning.service.LearningRecordService
import org.junit.jupiter.api.Test
import org.mockito.Mockito.*
import org.springframework.web.client.RestClient
import java.time.Duration
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.test.*

class GuardianshipRecordsTest {
    private val user=UUID.randomUUID()
    private val students=List(3) { LinkedStudent(UUID.randomUUID(),"child-$it",3,2017) }
    private val access=mock(StudentAccessService::class.java)
    private val consent=mock(ConsentAccessService::class.java)
    private val pins=mock(com.sagomungchi.core.guardianship.service.StudentPinService::class.java).also { mock ->
        students.forEach { `when`(mock.state(it.id)).thenReturn(com.sagomungchi.core.guardianship.domain.PinState(false,false)) }
    }
    private fun guardianship(records: LearningRecordService) = GuardianshipService(mock(StudentAccessRepository::class.java),access,
        mock(AccountAccessService::class.java),mock(ConsentService::class.java),consent,records,pins)
    private fun records(stub: LearningHttpStub) = LearningRecordService(LearningRecordClient(LearningClient(
        InternalRestClientFactory(AppProperties(AppProperties.Internal("server-secret",Duration.ofSeconds(1),Duration.ofSeconds(30)),
            mapOf("learning" to stub.url)),RestClient.builder()),LearningHttpProperties(Duration.ofSeconds(10))),jacksonObjectMapper()),
        access, mock(StudentLearningContextService::class.java))

    @Test fun `three actual HTTP requests overlap with verified context and preserve child order`() = LearningHttpStub().use { stub ->
        `when`(access.linkedStudents(user)).thenReturn(students)
        students.forEach { `when`(consent.hasGuardianConsent(user,it.id)).thenReturn(true) }
        val context=UserContext(user.toString(),"PARENT",students.map { it.id.toString() }.toSet(),"trace-records")
        val allArrived=CountDownLatch(3)
        stub.respond={ request ->
            assertEquals(user.toString(),request.header("X-User-Id"))
            assertEquals("PARENT",request.header("X-User-Role"))
            assertEquals(context.studentScope,request.header("X-Student-Scope")!!.split(',').toSet())
            assertEquals("server-secret",request.header("X-Internal-Token"))
            val id=request.target.substringAfter("/students/").substringBefore('/')
            allArrived.countDown();assertTrue(allArrived.await(5,TimeUnit.SECONDS),"All three requests must arrive before responding")
            LearningHttpStub.Reply(body="{\"studentId\":\"$id\",\"hasRecords\":${id!=students[0].id.toString()}}")
        }
        UserContextHolder.set(context)
        try {
            val rows=guardianship(records(stub)).children(user)
            assertEquals(students.map { it.id },rows.map { it.id })
            assertEquals(listOf(false,true,true),rows.map { it.hasRecords })
            assertTrue(rows.all { it.recordState=="AVAILABLE" })
            assertEquals(3,stub.requests.size)
            assertEquals(context,UserContextHolder.currentOrNull())
        } finally { UserContextHolder.clear() }
    }
    @Test fun `blocked child skips remote read while availability and false remain distinct`() {
        `when`(access.linkedStudents(user)).thenReturn(students)
        students.forEachIndexed { index,c -> `when`(consent.hasGuardianConsent(user,c.id)).thenReturn(index!=2) }
        val records=mock(LearningRecordService::class.java)
        `when`(records.exists(students[0].id)).thenReturn(null)
        `when`(records.exists(students[1].id)).thenReturn(false)
        val context=UserContext(user.toString(),"PARENT",students.take(2).map { it.id.toString() }.toSet(),null)
        UserContextHolder.set(context)
        try {
            val rows=guardianship(records).children(user)
            assertEquals(listOf("UNAVAILABLE","AVAILABLE","CONSENT_REQUIRED"),rows.map { it.recordState })
            assertEquals(listOf(null,false,null),rows.map { it.hasRecords })
            verify(records,never()).exists(students[2].id)
            assertEquals(context,UserContextHolder.currentOrNull())
        } finally { UserContextHolder.clear() }
    }
    @Test fun `worker authorization error is propagated without replacing it with false`() {
        `when`(access.linkedStudents(user)).thenReturn(students.take(1))
        `when`(consent.hasGuardianConsent(user,students[0].id)).thenReturn(true)
        val records=mock(LearningRecordService::class.java)
        `when`(records.exists(students[0].id)).thenThrow(BusinessException(org.springframework.http.HttpStatus.FORBIDDEN,"FORBIDDEN","scope"))
        val context=UserContext(user.toString(),"PARENT",emptySet(),null);UserContextHolder.set(context)
        try {
            assertEquals("FORBIDDEN",assertFailsWith<BusinessException> { guardianship(records).children(user) }.code)
            assertEquals(context,UserContextHolder.currentOrNull())
        } finally { UserContextHolder.clear() }
    }
}
