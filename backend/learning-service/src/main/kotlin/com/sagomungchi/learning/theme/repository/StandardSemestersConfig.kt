package com.sagomungchi.learning.theme.repository

import com.sagomungchi.learning.theme.domain.StandardSemesters
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.core.io.ClassPathResource

/**
 * #536 성취기준 학기 대응표를 resources/knowledge/semester_map.csv에서 시작 때 한 번 읽음. 파일이 없거나 형식이 다르면 시작 실패.
 * 지식 판 적재·활성화(#466)나 DB에 기대지 않음(RAG를 쓰지 않음, 팀 결정 2026-11-11)
 */
@Configuration(proxyBeanMethods = false)
class StandardSemestersConfig {
    @Bean
    fun standardSemesters(): StandardSemesters = load()

    companion object {
        const val RESOURCE = "knowledge/semester_map.csv"

        fun load(): StandardSemesters =
            StandardSemesters.parse(ClassPathResource(RESOURCE).inputStream.use { it.readBytes().toString(Charsets.UTF_8) })
    }
}
