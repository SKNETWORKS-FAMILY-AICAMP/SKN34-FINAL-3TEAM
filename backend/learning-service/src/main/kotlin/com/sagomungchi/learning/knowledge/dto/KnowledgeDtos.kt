package com.sagomungchi.learning.knowledge.dto

import com.fasterxml.jackson.annotation.JsonSetter
import com.fasterxml.jackson.annotation.Nulls

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

data class SearchFilters(
    @param:JsonSetter(nulls = Nulls.FAIL, contentNulls = Nulls.FAIL) val kinds: List<String> = emptyList(),
    @param:JsonSetter(nulls = Nulls.FAIL, contentNulls = Nulls.FAIL) val subjects: List<String> = emptyList(),
    @param:JsonSetter(nulls = Nulls.FAIL, contentNulls = Nulls.FAIL) val grades: List<Int> = emptyList(),
    @param:JsonSetter(nulls = Nulls.FAIL, contentNulls = Nulls.FAIL) val semesters: List<String> = emptyList(),
    @param:JsonSetter(nulls = Nulls.FAIL, contentNulls = Nulls.FAIL) val thinkingTypes: List<String> = emptyList(),
)
data class SearchRequest(
    @param:JsonSetter(contentNulls = Nulls.FAIL) val vector: List<Double>,
    val embeddingModel: String,
    @param:JsonSetter(nulls = Nulls.FAIL) val k: Int? = null,
    @param:JsonSetter(nulls = Nulls.FAIL) val minSimilarity: Double? = null,
    @param:JsonSetter(nulls = Nulls.FAIL) val filters: SearchFilters = SearchFilters(),
)
data class SearchHit(
    val ref: KnowledgeRef, val kind: String, val subject: String?, val area: String?, val standardCode: String?,
    val domainId: String?, val thinkingType: String?, val grades: List<Int>, val semesters: List<String>,
    val text: String, val similarity: Double,
)
data class SearchResponse(val datasetVersion: String?, val items: List<SearchHit>, val reason: String?)
data class ThemeCandidatesRequest(
    @param:JsonSetter(contentNulls = Nulls.FAIL) val vector: List<Double>,
    val embeddingModel: String, val grade: Int, val semester: String,
    @param:JsonSetter(nulls = Nulls.FAIL) val k: Int? = null,
    @param:JsonSetter(nulls = Nulls.FAIL) val minSimilarity: Double? = null,
)
data class ThemeCandidate(
    val code: String, val statement: String, val subject: String, val area: String, val similarity: Double,
    val matchedBy: KnowledgeRef, val fitReason: String, val ref: KnowledgeRef,
)
data class ThemeTypeCandidates(val thinkingType: String, val candidates: List<ThemeCandidate>, val reason: String?)
data class ThemeCandidatesResponse(val datasetVersion: String?, val grade: Int, val semester: String, val types: List<ThemeTypeCandidates>, val reason: String?)
data class LearnedConcept(val text: String, @param:JsonSetter(contentNulls = Nulls.FAIL) val vector: List<Double>)
data class LearnedRequest(
    @param:JsonSetter(contentNulls = Nulls.FAIL) val concepts: List<LearnedConcept>,
    val embeddingModel: String, val grade: Int, val semester: String,
    @param:JsonSetter(nulls = Nulls.FAIL) val minSimilarity: Double? = null,
)
data class LearnedMatch(val contentId: String, val text: String, val similarity: Double, val ref: KnowledgeRef)
data class LearnedIn(val standardCode: String, val semester: String)
data class LearnedItem(val text: String, val verdict: String, val matched: LearnedMatch?, val learnedIn: List<LearnedIn>, val reason: String?)
data class LearnedResponse(val datasetVersion: String?, val grade: Int, val semester: String, val items: List<LearnedItem>, val reason: String?)
