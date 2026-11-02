package com.sagomungchi.core.report.repository

import com.fasterxml.jackson.databind.ObjectMapper
import com.sagomungchi.core.report.domain.ReportTemplateSettings
import com.sagomungchi.core.report.domain.ReportTemplateSnapshot
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.stereotype.Repository
import java.time.OffsetDateTime
import java.util.UUID

@Repository
class ReportTemplateRepository(private val jdbc: JdbcTemplate, private val json: ObjectMapper) {
    // All mutations are serialized by the existing parent account lock, across replicas.
    fun get(parent: UUID): ReportTemplateSnapshot = jdbc.query(
        "SELECT settings::text,revision FROM parent_report_template WHERE parent_user_id=?",
        { r, _ -> ReportTemplateSnapshot(json.readValue(r.getString(1), ReportTemplateSettings::class.java).validate(), r.getLong(2)) }, parent
    ).singleOrNull() ?: ReportTemplateSnapshot(ReportTemplateSettings(), 0)

    fun propose(parent: UUID, conversation: UUID, id: UUID, settings: ReportTemplateSettings, expires: OffsetDateTime) {
        jdbc.update("""INSERT INTO parent_report_template(parent_user_id,settings,revision,proposal_id,
            proposal_conversation_id,proposal_settings,proposal_expires_at,updated_at)
            VALUES(?,?::jsonb,0,?,?,?::jsonb,?,?)
            ON CONFLICT(parent_user_id) DO UPDATE SET proposal_id=EXCLUDED.proposal_id,
            proposal_conversation_id=EXCLUDED.proposal_conversation_id,proposal_settings=EXCLUDED.proposal_settings,
            proposal_expires_at=EXCLUDED.proposal_expires_at,updated_at=EXCLUDED.updated_at""",
            parent,json.writeValueAsString(ReportTemplateSettings()),id,conversation,json.writeValueAsString(settings),expires,OffsetDateTime.now())
    }
    fun confirm(parent: UUID, conversation: UUID, proposal: UUID): Boolean = jdbc.update("""
        UPDATE parent_report_template SET settings=proposal_settings,revision=revision+1,
        proposal_id=NULL,proposal_conversation_id=NULL,proposal_settings=NULL,proposal_expires_at=NULL,updated_at=?
        WHERE parent_user_id=? AND proposal_id=? AND proposal_conversation_id=? AND proposal_expires_at>?
        """,OffsetDateTime.now(),parent,proposal,conversation,OffsetDateTime.now()) == 1
}
