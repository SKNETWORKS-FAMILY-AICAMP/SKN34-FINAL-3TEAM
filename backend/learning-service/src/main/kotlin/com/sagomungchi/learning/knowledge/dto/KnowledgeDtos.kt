package com.sagomungchi.learning.knowledge.dto


/** C5 JSON names match the ai-service Pydantic contracts; null response fields are intentional. */
data class KnowledgeRef(val kind: String, val id: String, val datasetVersion: String)
data class ContentItem(val group: String?, val text: String)
data class StandardView(
    val code: String, val subject: String, val grades: List<Int>, val semesters: List<String>,
    val noticeGradeBand: String, val area: String, val statement: String, val explanation: String?, val ref: KnowledgeRef,
)
data class DomainView(
    val id: String, val subject: String, val area: String, val scope: String, val coreIdeas: List<String>,
    val knowledge: List<ContentItem>, val process: List<ContentItem>, val values: List<ContentItem>,
    val considerations: List<String>, val activities: List<String>, val ref: KnowledgeRef,
)
data class ContentView(val id: String, val domainId: String, val category: String, val group: String?, val text: String, val ref: KnowledgeRef)
data class FitView(val thinkingType: String, val reason: String)
data class StandardBundle(val standard: StandardView, val domain: DomainView?, val covers: List<ContentView>, val fits: List<FitView>, val gradeMatch: Boolean?)
data class SubjectGuideView(val subject: String, val teaching: List<String>, val assessment: List<String>, val ref: KnowledgeRef)
data class ThinkingTypeBasis(val framework: String, val attribution: String)
data class ThinkingTypeElement(val code: String, val label: String, val description: String)
data class ThinkingTypeGuide(
    val type: String, val name: String, val basis: List<ThinkingTypeBasis>, val elements: List<ThinkingTypeElement>,
    val questionMust: List<String>, val questionMustNot: List<String>, val ref: KnowledgeRef,
)
data class KnowledgeBundle(
    val datasetVersion: String?, val items: List<StandardBundle>, val missingCodes: List<String>,
    val subjectGuides: List<SubjectGuideView>, val thinkingType: ThinkingTypeGuide?, val reason: String?,
)
data class ThinkingTypeResponse(val datasetVersion: String?, val guide: ThinkingTypeGuide?, val reason: String?)
