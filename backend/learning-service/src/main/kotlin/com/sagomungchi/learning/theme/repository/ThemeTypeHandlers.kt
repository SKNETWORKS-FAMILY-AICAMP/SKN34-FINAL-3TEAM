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

/** 구체 타입으로만 등록하고 XML typeHandler로 지정. 움직임 JSON은 mission.repository.MotionTypeHandler(미션 장면과 함께 씀) */
@Configuration(proxyBeanMethods = false)
class ThemePersistenceConfig {
    @Bean
    fun themeJsonbTypes(objectMapper: ObjectMapper) = ConfigurationCustomizer { configuration ->
        configuration.typeHandlerRegistry.apply {
            register(object : TypeReference<List<DialogueLine>>() {}, DialogueListTypeHandler(objectMapper))
            register(object : TypeReference<List<HintSpot>>() {}, HintSpotListTypeHandler(objectMapper))
        }
    }
}
