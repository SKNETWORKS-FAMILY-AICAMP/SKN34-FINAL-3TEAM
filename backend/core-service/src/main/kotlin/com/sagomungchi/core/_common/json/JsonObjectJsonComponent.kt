package com.sagomungchi.core._common.json

import com.fasterxml.jackson.core.JsonGenerator
import com.fasterxml.jackson.core.JsonParser
import com.fasterxml.jackson.databind.DeserializationContext
import com.fasterxml.jackson.databind.JsonDeserializer
import com.fasterxml.jackson.databind.JsonSerializer
import com.fasterxml.jackson.databind.SerializerProvider
import org.springframework.boot.jackson.JsonComponent

/** JsonObject ↔ JSON 객체. 응답·스냅샷 모양은 감싼 Map 그대로 (#168) */
@JsonComponent
class JsonObjectJsonComponent {
    class Serializer : JsonSerializer<JsonObject>() {
        override fun serialize(value: JsonObject, gen: JsonGenerator, serializers: SerializerProvider) =
            serializers.defaultSerializeValue(value.values, gen)
    }

    class Deserializer : JsonDeserializer<JsonObject>() {
        override fun deserialize(p: JsonParser, ctxt: DeserializationContext): JsonObject =
            JsonObject(ctxt.readValue(p, ctxt.typeFactory.constructMapType(LinkedHashMap::class.java, String::class.java, Any::class.java)))
    }
}
