package com.sagomungchi.learning.theme.repository

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.persistence.JacksonJsonbTypeHandler
import com.sagomungchi.learning.theme.domain.DialogueLine
import com.sagomungchi.learning.theme.domain.HintSpot
import org.apache.ibatis.type.TypeReference
import org.mybatis.spring.boot.autoconfigure.ConfigurationCustomizer
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

/** weekly_theme_day.dialogue: 문제 전 대화 [{speaker, text}] (#438) */
class DialogueListTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<List<DialogueLine>>(
    objectMapper, objectMapper.typeFactory.constructCollectionType(List::class.java, DialogueLine::class.java),
)

/** weekly_theme_day.hint_spots: 그림 위 생각 열기 위치 [{seq, x, y}] (#438) */
class HintSpotListTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<List<HintSpot>>(
    objectMapper, objectMapper.typeFactory.constructCollectionType(List::class.java, HintSpot::class.java),
)

/** weekly_theme_version.intro_motion·outro_motion, mission_version.scene_motion: ai가 정한 움직임 JSON 객체 그대로 (#438) */
class MotionTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<Map<String, Any?>>(
    objectMapper, objectMapper.typeFactory.constructMapType(Map::class.java, String::class.java, Any::class.java),
)

/**
 * 구체 타입으로 등록하고 XML typeHandler로 지정. 움직임의 Map<String, Any?>는 판정 ContentMapTypeHandler와 같은 타입이라 전역 매핑이 겹치지만
 * 둘 다 같은 방식으로 읽고 쓰며, 각 XML이 자기 핸들러 클래스를 지정한다
 */
@Configuration(proxyBeanMethods = false)
class ThemePersistenceConfig {
    @Bean
    fun themeJsonbTypes(objectMapper: ObjectMapper) = ConfigurationCustomizer { configuration ->
        configuration.typeHandlerRegistry.apply {
            register(object : TypeReference<List<DialogueLine>>() {}, DialogueListTypeHandler(objectMapper))
            register(object : TypeReference<List<HintSpot>>() {}, HintSpotListTypeHandler(objectMapper))
            register(object : TypeReference<Map<String, Any?>>() {}, MotionTypeHandler(objectMapper))
        }
    }
}
