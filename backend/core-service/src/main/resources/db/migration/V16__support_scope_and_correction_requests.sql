-- Preserve legacy rows: never guess the role of a shared parent account.
ALTER TABLE error_report ADD COLUMN requester_role varchar,
 ADD COLUMN requester_student_id uuid REFERENCES student(id), ADD COLUMN attempt_id uuid,
 ADD COLUMN submission_key uuid,
 ADD CONSTRAINT ck_error_report_requester_role CHECK(requester_role IN ('STUDENT','PARENT')),
 ADD CONSTRAINT ck_error_report_requester_scope CHECK(requester_role IS NULL OR
   (requester_role='STUDENT' AND requester_student_id IS NOT NULL) OR
   (requester_role='PARENT' AND requester_student_id IS NULL)),
 ADD CONSTRAINT uq_error_report_submission UNIQUE(reporter_user_id,submission_key);
ALTER TABLE inquiry ADD COLUMN requester_role varchar, ADD COLUMN student_id uuid REFERENCES student(id),
 ADD COLUMN requester_student_id uuid REFERENCES student(id), ADD COLUMN attempt_id uuid,
 ADD CONSTRAINT ck_inquiry_requester_role CHECK(requester_role IN ('STUDENT','PARENT')),
 ADD CONSTRAINT ck_inquiry_requester_scope CHECK(requester_role IS NULL OR
   (requester_role='STUDENT' AND requester_student_id IS NOT NULL AND student_id=requester_student_id) OR
   (requester_role='PARENT' AND requester_student_id IS NULL));
ALTER TABLE correction ADD COLUMN request_key uuid, ADD COLUMN corrected varchar,
 ADD COLUMN previous_result varchar, ADD COLUMN processing_status varchar,
 ADD COLUMN provider_result jsonb, ADD COLUMN completed_at timestamptz,
 ADD CONSTRAINT ck_correction_processing_status CHECK(processing_status IN ('PENDING','FAILED','COMPLETED')),
 ADD CONSTRAINT ck_correction_corrected CHECK(corrected IN ('CORRECT','PARTIAL','RETHINK','HELD')),
 ADD CONSTRAINT uq_correction_request UNIQUE(request_key);
CREATE UNIQUE INDEX uq_correction_report_request ON correction(error_report_id) WHERE request_key IS NOT NULL;
