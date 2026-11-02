package com.sagomungchi.core.guardianship

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core._common.security.UserContext
import com.sagomungchi.core._common.security.UserContextHolder
import com.sagomungchi.core.guardianship.domain.StudentLearningContext
import com.sagomungchi.core.guardianship.repository.StudentLearningContextRepository
import com.sagomungchi.core.guardianship.service.StudentLearningContextService
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.mockito.Mockito.*
import java.util.UUID
import kotlin.test.*

class StudentSharingTest {
    private val repository = mock(StudentLearningContextRepository::class.java)
    private val service = StudentLearningContextService(repository)
    private val user = UUID.randomUUID()
    private val student = UUID.randomUUID()
    private fun context(role: String = "STUDENT", scope: Set<String> = setOf(student.toString())) {
        UserContextHolder.set(UserContext(user.toString(), role, scope, null))
    }
    @AfterEach fun clear() = UserContextHolder.clear()

    @Test fun `student reads private and explicitly opts in then out without changing another child`() {
        context()
        `when`(repository.findLinked(user, student)).thenReturn(StudentLearningContext(3, false))
        `when`(repository.sharingEnabled(student)).thenReturn(false)
        `when`(repository.updateSharing(student, true)).thenReturn(1)
        `when`(repository.updateSharing(student, false)).thenReturn(1)
        assertFalse(service.ownSharing().parentSharingEnabled)
        assertTrue(service.ownSharing(true).parentSharingEnabled)
        assertFalse(service.ownSharing(false).parentSharingEnabled)
        verify(repository).updateSharing(student, true)
        verify(repository).updateSharing(student, false)
    }

    @Test fun `parent administrator system or multi-child context cannot change preference`() {
        for (role in listOf("PARENT", "ADMIN", "SYSTEM")) {
            context(role)
            assertEquals("FORBIDDEN", assertFailsWith<BusinessException> { service.ownSharing(true) }.code)
        }
        context(scope = setOf(student.toString(), UUID.randomUUID().toString()))
        assertFailsWith<BusinessException> { service.ownSharing(true) }
        verifyNoInteractions(repository)
    }

    @Test fun `unlinked or inactive student does not get a successful setting response`() {
        context()
        assertEquals("CHILD_NOT_LINKED", assertFailsWith<BusinessException> { service.ownSharing(true) }.code)
        `when`(repository.findLinked(user, student)).thenReturn(StudentLearningContext(3, false))
        `when`(repository.sharingEnabled(student)).thenReturn(null)
        assertEquals("NOT_FOUND", assertFailsWith<BusinessException> { service.ownSharing() }.code)
        verify(repository, never()).updateSharing(student, true)
    }

    @Test fun `parent can only read a linked in-scope child and cannot force sharing`() {
        context("PARENT")
        `when`(repository.findLinked(user, student)).thenReturn(StudentLearningContext(3, false))
        `when`(repository.sharingEnabled(student)).thenReturn(false)
        assertFalse(service.parentSharing(student).parentSharingEnabled)
        assertEquals("FORBIDDEN", assertFailsWith<BusinessException> { service.parentSharing(UUID.randomUUID()) }.code)
        verify(repository, never()).updateSharing(student, true)
    }

    @Test fun `private records gate rejects originals but a later explicit opt-in is observed`() {
        `when`(repository.sharingEnabled(student)).thenReturn(false, true, false)
        assertEquals("STUDENT_RECORDS_PRIVATE", assertFailsWith<BusinessException> { service.requireShared(student) }.code)
        service.requireShared(student)
        assertEquals("STUDENT_RECORDS_PRIVATE", assertFailsWith<BusinessException> { service.requireShared(student) }.code)
    }
}
