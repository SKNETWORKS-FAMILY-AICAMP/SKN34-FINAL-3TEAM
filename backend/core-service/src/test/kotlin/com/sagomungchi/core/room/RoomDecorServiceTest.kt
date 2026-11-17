package com.sagomungchi.core.room

import com.sagomungchi.core._common.exception.BusinessException
import com.sagomungchi.core.reward.service.RewardAccessService
import com.sagomungchi.core.room.repository.RoomDecorMapper
import com.sagomungchi.core.room.service.RoomDecorService
import org.junit.jupiter.api.Test
import org.mockito.Mockito.*
import org.springframework.http.HttpStatus
import java.util.UUID
import kotlin.test.*

class RoomDecorServiceTest {
    @Test fun `student becoming unavailable after access check cannot replace placements`() {
        val mapper = mock(RoomDecorMapper::class.java)
        val access = mock(RewardAccessService::class.java)
        val student = UUID.randomUUID()
        `when`(access.currentStudent()).thenReturn(student)
        `when`(mapper.lockActiveStudent(student)).thenReturn(null)
        val error = assertFailsWith<BusinessException> {
            RoomDecorService(mapper, access).replace(listOf(RoomDecorService.SpotInput("FLOOR", 0, 0, "POT")))
        }
        assertEquals(HttpStatus.CONFLICT, error.status)
        assertEquals("STUDENT_UNAVAILABLE", error.code)
        verify(mapper).lockActiveStudent(student)
        verifyNoMoreInteractions(mapper)
    }
}
