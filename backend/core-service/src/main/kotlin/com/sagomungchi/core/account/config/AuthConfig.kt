package com.sagomungchi.core.account.config

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core._common.security.PublicAuthFilter
import com.sagomungchi.core.account.service.AuthService
import org.springframework.boot.web.servlet.FilterRegistrationBean
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

@Configuration
class AuthConfig {
    @Bean
    fun publicAuthFilter(service: AuthService, properties: AuthProperties, json: ObjectMapper) =
        FilterRegistrationBean(PublicAuthFilter(service, properties, json)).apply { order = 20 }
}
