package com.sagomungchi.learning.mission.repository

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.learning._common.persistence.JacksonJsonbTypeHandler
import com.sagomungchi.learning.mission.domain.AnswerKey
import com.sagomungchi.learning.mission.domain.Category
import com.sagomungchi.learning.mission.domain.Choice
import org.apache.ibatis.type.TypeReference
import org.mybatis.spring.boot.autoconfigure.ConfigurationCustomizer
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

/** mission_version.choices: [{id, label}] */
class ChoiceListTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<List<Choice>>(
    objectMapper, objectMapper.typeFactory.constructCollectionType(List::class.java, Choice::class.java),
)

/** mission_version.categories: 분류 그룹 [{id, label}] */
class CategoryListTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<List<Category>>(
    objectMapper, objectMapper.typeFactory.constructCollectionType(List::class.java, Category::class.java),
)

/** mission_version.input_template: 풀이 단계·논술 틀 칸 이름 */
class StringListTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<List<String>>(
    objectMapper, objectMapper.typeFactory.constructCollectionType(List::class.java, String::class.java),
)

/** rubric_version.answer_key: 정답 키 */
class AnswerKeyTypeHandler(objectMapper: ObjectMapper) : JacksonJsonbTypeHandler<AnswerKey>(
    objectMapper, objectMapper.typeFactory.constructType(AnswerKey::class.java),
)

/**
 * 요소 타입까지 지정한 핸들러를 그 타입에만 등록 (repository-foundation 보고서).
 * Mapper XML은 typeHandler로 이 인스턴스를 사용하고, 일반 List에는 적용되지 않음.
 */
@Configuration(proxyBeanMethods = false)
class MissionPersistenceConfig {
    @Bean
    fun missionJsonbTypes(objectMapper: ObjectMapper) = ConfigurationCustomizer { configuration ->
        with(configuration.typeHandlerRegistry) {
            register(object : TypeReference<List<Choice>>() {}, ChoiceListTypeHandler(objectMapper))
            register(object : TypeReference<List<Category>>() {}, CategoryListTypeHandler(objectMapper))
            register(object : TypeReference<List<String>>() {}, StringListTypeHandler(objectMapper))
            register(AnswerKey::class.java, AnswerKeyTypeHandler(objectMapper))
        }
    }
}
