package com.sagomungchi.learning.attempt.repository

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.persistence.JacksonJsonbTypeHandler
import com.sagomungchi.learning.attempt.domain.DraftContent
import org.mybatis.spring.boot.autoconfigure.ConfigurationCustomizer
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

/** attempt_draft.content: {answer, memo} */
class DraftContentTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<DraftContent>(
    objectMapper, objectMapper.typeFactory.constructType(DraftContent::class.java),
)

/** 구조가 고정된 jsonb DTO 타입에만 등록 (repository-foundation 보고서) */
@Configuration(proxyBeanMethods = false)
class AttemptPersistenceConfig {
    @Bean
    fun attemptJsonbTypes(objectMapper: ObjectMapper) = ConfigurationCustomizer { configuration ->
        configuration.typeHandlerRegistry.register(DraftContent::class.java, DraftContentTypeHandler(objectMapper))
    }
}
