-- A full generation starts a story. Partial regenerations share its scenes and keep their own output.
ALTER TABLE theme_draft ADD COLUMN family_root_id uuid;
ALTER TABLE theme_draft ADD COLUMN frozen_scene_choices jsonb;
ALTER TABLE theme_draft ADD CONSTRAINT fk_theme_draft_family_root
    FOREIGN KEY (family_root_id) REFERENCES theme_draft (id);

WITH RECURSIVE lineage(id, root_id) AS (
    SELECT d.id, d.id FROM theme_draft d
    WHERE NOT EXISTS (SELECT 1 FROM theme_draft p WHERE p.id::text = d.input #>> '{regenerate,baseDraftId}')
    UNION ALL
    SELECT child.id, parent.root_id FROM lineage parent
    JOIN theme_draft child ON child.input #>> '{regenerate,baseDraftId}' = parent.id::text
)
UPDATE theme_draft d SET family_root_id = lineage.root_id
FROM lineage WHERE d.id = lineage.id AND lineage.id <> lineage.root_id;

CREATE INDEX ix_theme_draft_family_root ON theme_draft (family_root_id, created_at);

CREATE TABLE theme_draft_scene_selection (
    root_id uuid NOT NULL REFERENCES theme_draft (id),
    scene varchar NOT NULL CHECK (scene IN ('INTRO','MON','TUE','WED','THU','FRI','OUTRO')),
    version_id uuid NOT NULL REFERENCES theme_draft (id),
    reviewed_version_ids uuid[] NOT NULL,
    confirmed_at timestamptz NOT NULL,
    PRIMARY KEY (root_id, scene)
);

CREATE TABLE theme_draft_scene_note (
    version_id uuid NOT NULL REFERENCES theme_draft (id),
    scene varchar NOT NULL CHECK (scene IN ('INTRO','MON','TUE','WED','THU','FRI','OUTRO')),
    starred boolean NOT NULL,
    note varchar(160) NOT NULL,
    PRIMARY KEY (version_id, scene)
);
