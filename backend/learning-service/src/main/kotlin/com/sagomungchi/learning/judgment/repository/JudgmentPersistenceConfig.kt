package com.sagomungchi.learning.judgment.repository

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.persistence.JacksonJsonbTypeHandler
import org.apache.ibatis.type.TypeReference
import org.mybatis.spring.boot.autoconfigure.ConfigurationCustomizer
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

/** 타임라인의 답변 내용(jsonb)을 화면용 Map으로 */
class ContentMapTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<Map<String, Any?>>(
    objectMapper,
    objectMapper.typeFactory.constructMapType(Map::class.java, String::class.java, Any::class.java),
)

/** 일반 Map에 전역 적용되지 않도록 구체 타입으로만 등록하고 XML typeHandler로 지정 */
@Configuration(proxyBeanMethods = false)
class JudgmentPersistenceConfig {
    @Bean
    fun judgmentJsonbTypes(objectMapper: ObjectMapper) = ConfigurationCustomizer { configuration ->
        configuration.typeHandlerRegistry.register(object : TypeReference<Map<String, Any?>>() {}, ContentMapTypeHandler(objectMapper))
    }
}
