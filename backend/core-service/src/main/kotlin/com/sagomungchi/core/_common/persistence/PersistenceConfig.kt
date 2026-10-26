package com.sagomungchi.core._common.persistence

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import org.apache.ibatis.type.OffsetDateTimeTypeHandler
import org.mybatis.spring.boot.autoconfigure.ConfigurationCustomizer
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import java.time.Instant
import java.time.OffsetDateTime
import java.util.UUID

@Configuration(proxyBeanMethods = false)
class PersistenceConfig {
    @Bean
    fun postgresTypes(objectMapper: ObjectMapper) = ConfigurationCustomizer { configuration ->
        with(configuration.typeHandlerRegistry) {
            register(UUID::class.java, UuidTypeHandler())
            register(Instant::class.java, InstantTypeHandler())
            register(OffsetDateTime::class.java, OffsetDateTimeTypeHandler())
            register(JsonNode::class.java, JsonNodeTypeHandler(objectMapper))
        }
    }
}
