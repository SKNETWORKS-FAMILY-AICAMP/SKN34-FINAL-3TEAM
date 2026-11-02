-- Prepare P01/P13 fields without inventing values for existing records.
-- For a populated DB, migrate to target=6, supply reviewed values, then apply V7.
-- See docs/report/db-policy-schema.md. No seeds or destructive data rewrite.

ALTER TABLE student ADD COLUMN birth_year integer;
ALTER TABLE product ADD COLUMN limits jsonb;

-- P13 allows additional plans and new product rows for changed prices/limits.
-- Keep product.code UNIQUE; FREE/PREMIUM are initial codes, not a closed enum.
-- Existing BASIC/PLUS rows are retained as historical products, not relabeled.
ALTER TABLE product DROP CONSTRAINT ck_product_code;
