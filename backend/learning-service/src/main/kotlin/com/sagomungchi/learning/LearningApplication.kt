package com.sagomungchi.learning

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.context.properties.ConfigurationPropertiesScan
import org.springframework.boot.runApplication

@SpringBootApplication
@ConfigurationPropertiesScan
class LearningApplication

fun main(args: Array<String>) {
    runApplication<LearningApplication>(*args)
}
