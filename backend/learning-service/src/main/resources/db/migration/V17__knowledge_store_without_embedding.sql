-- #466 정리: 미션·테마 생성에 벡터 검색·임베딩을 쓰지 않기로 한 팀 결정(에픽 #463, 2026-11-11).
-- 지식 표는 성취기준·생각 유형 코드 조회용으로 남기고 임베딩 칸·벡터 인덱스·모델 칸만 지운다.
-- vector 확장은 V14가 처음부터 다시 적용될 때 필요하므로 그대로 둔다(bootstrap).
DROP INDEX knowledge_chunk_embedding_hnsw;
ALTER TABLE knowledge_chunk DROP COLUMN embedding;
ALTER TABLE knowledge_dataset DROP COLUMN embedding_model, DROP COLUMN embedding_dimensions;
