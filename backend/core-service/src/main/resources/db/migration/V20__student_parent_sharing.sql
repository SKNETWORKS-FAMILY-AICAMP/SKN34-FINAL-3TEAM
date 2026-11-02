-- Student-controlled, fail-closed default applies to existing and new students.
ALTER TABLE student ADD COLUMN parent_sharing_enabled boolean NOT NULL DEFAULT false;
