package com.sagomungchi.learning.wordhelp.domain

data class WordHelpResult(
    val state: String,
    val headword: String?,
    val text: String,
    val example: String?,
    val senses: List<WordSense>,
)

data class WordSense(
    val definition: String,
    val source: String,
    val attribution: String? = null,
    val sourceUrl: String? = null,
    val license: String? = null,
)
