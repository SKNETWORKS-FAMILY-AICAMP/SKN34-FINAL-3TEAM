package com.sagomungchi.learning.answer.repository

import com.fasterxml.jackson.annotation.JsonInclude
import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.persistence.JacksonJsonbTypeHandler
import com.sagomungchi.learning.answer.domain.AnswerContent
import org.mybatis.spring.boot.autoconfigure.ConfigurationCustomizer
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

/** answer.content: 입력 방식에 쓰는 필드만, 비어 있는 필드는 저장하지 않음 */
class AnswerContentTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<AnswerContent>(
    objectMapper.copy().setSerializationInclusion(JsonInclude.Include.NON_NULL),
    objectMapper.typeFactory.constructType(AnswerContent::class.java),
)

/** 구조가 고정된 jsonb DTO 타입에만 등록 (repository-foundation 보고서) */
@Configuration(proxyBeanMethods = false)
class AnswerPersistenceConfig {
    @Bean
    fun answerJsonbTypes(objectMapper: ObjectMapper) = ConfigurationCustomizer { configuration ->
        configuration.typeHandlerRegistry.register(AnswerContent::class.java, AnswerContentTypeHandler(objectMapper))
    }
}
