package com.sagomungchi.core._common.json

/**
 * jsonb 객체 값(상품 features·limits·상품 스냅샷). domain이 Jackson JsonNode 없이 JSON 객체를 들게 함 (아키텍처 2.1, #168).
 * JSON 변환은 JsonObjectJsonComponent, DB 변환은 JsonObjectTypeHandler. 값은 Jackson 기본 변환대로 Int·Long·Double·Boolean·String·List·Map
 */
data class JsonObject(val values: Map<String, Any?>) {
    operator fun get(key: String): Any? = values[key]
}
