package com.sagomungchi.core.support

import com.sagomungchi.core._common.persistence.PostgresRepositoryTest
import com.sagomungchi.core.support.repository.SupportRepository
import com.sagomungchi.core.support.domain.*
import com.sagomungchi.core.report.parent
import com.sagomungchi.core.report.child
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import java.util.UUID
import java.time.OffsetDateTime
import kotlin.test.*

class SupportRepositoryTest: PostgresRepositoryTest() {
 @Autowired lateinit var repository: SupportRepository
 @Autowired lateinit var jdbc: JdbcTemplate
 @Test fun `nullable legacy ownership never appears in parent or student lists and row maps preserve scope`() {
  val user=parent(jdbc);val student=child(jdbc,user);val now=OffsetDateTime.now()
  val value=SupportReport(UUID.randomUUID(),user,null,null,student,null,null,"JUDGMENT",UUID.randomUUID(),"OTHER",null,"RECEIVED",null,null,null,now,null)
  repository.mapper.insertReport(value)
  assertEquals(value.id,repository.mapper.report(value.id)!!.id)
  assertEquals(0L,repository.mapper.reportCount(user,"PARENT",null,setOf(student),null))
  assertEquals(0L,repository.mapper.reportCount(user,"STUDENT",student,setOf(student),null))
  val owner=value.copy(id=UUID.randomUUID(),requesterRole="STUDENT",requesterStudentId=student,submissionKey=UUID.randomUUID())
  repository.mapper.insertReport(owner)
  assertEquals(student,repository.mapper.report(owner.id)!!.requesterStudentId)
  assertEquals(1L,repository.mapper.reportCount(user,"STUDENT",student,setOf(student),null))
  assertEquals(0L,repository.mapper.reportCount(user,"STUDENT",student,emptySet(),null))
 }
 @Test fun `correction history retains previous result reason timestamp and serialized provider result`() {
  val user=parent(jdbc);val student=child(jdbc,user);val now=OffsetDateTime.now()
  val report=SupportReport(UUID.randomUUID(),user,"PARENT",null,student,UUID.randomUUID(),UUID.randomUUID(),"JUDGMENT",UUID.randomUUID(),"WRONG_JUDGMENT","확인","IN_REVIEW",null,null,null,now,null)
  repository.mapper.insertReport(report)
  val correction=Correction(UUID.randomUUID(),report.id,"JUDGMENT",report.targetId,UUID.randomUUID(),"사유","CORRECT","RETHINK","PENDING",null,null,user,now,null)
  repeat(2) { repository.mapper.insertCorrection(correction.copy(id=UUID.randomUUID(),requestKey=null,processingStatus=null,corrected=null)) }
  repository.mapper.insertCorrection(correction)
  assertEquals(3,repository.mapper.corrections(report.id).size)
  repository.mapper.updateCorrection(correction.copy(processingStatus="COMPLETED",impact="""{"report":"UNKNOWN"}""",providerResult="""{"correctionId":"provider"}""",completedAt=now))
  val saved=repository.mapper.correction(report.id)!!
  assertEquals("RETHINK",saved.previousResult);assertEquals("사유",saved.reason);assertEquals("COMPLETED",saved.processingStatus)
  assertTrue(saved.providerResult!!.contains("provider"));assertNotNull(saved.completedAt)
  assertEquals("IN_REVIEW",repository.mapper.report(report.id)!!.status)
 }
}
