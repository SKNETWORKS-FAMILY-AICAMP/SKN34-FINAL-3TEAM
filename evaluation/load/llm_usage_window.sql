-- 측정 구간의 ai LLM 호출 1회 지연·토큰·비용 (#630). core_db에서 실행한다.
--   psql -v from="'2026-11-16T05:00:00Z'" -v to="'2026-11-16T06:00:00Z'" -f evaluation/load/llm_usage_window.sql
-- est_cost_usd는 #651 단가(application.yml app.llm-pricing, 2026-11-16 OpenAI 공개 단가)로 토큰에서 다시 계산한 값이다.
-- 단가 등록 전 행(cost_usd null)도 같은 기준으로 비교하려고 둔다. 영상·sLLM은 토큰 단가가 없어 비어 있다.
-- from·to를 비우면 전체 기간. 대역·스텁 모델(토큰 1·memory-stub·theme-stub 등)은 실사용이 아니라 뺀다.
\if :{?from}
\else
  \set from '''-infinity'''
\endif
\if :{?to}
\else
  \set to '''infinity'''
\endif

with price(model, input_usd, output_usd) as (
    values ('gpt-6-luna', 0.10, 0.50), ('gpt-6.1-terra', 1.00, 5.00),
           ('text-embedding-3-small', 0.02, 0.0), ('gpt-image-2.6-sunburst', 8.00, 30.00)
),
real as (
    select *
    from llm_usage
    where occurred_at >= :from::timestamptz
      and occurred_at < :to::timestamptz
      and model not like '%stub%'
      and model not in ('report-explanation')
      -- 대역(llm-stub·sllm 대역)은 토큰을 1로 보낸다. 실패 호출(토큰 null)은 남긴다
      and not (input_tokens is not null and input_tokens <= 1 and coalesce(output_tokens, 0) <= 1)
)
select call_type,
       model,
       count(*)                                                              as calls,
       count(*) filter (where not success)                                   as failed,
       round(avg(input_tokens))                                              as avg_in,
       round(avg(output_tokens))                                             as avg_out,
       round(percentile_cont(0.5) within group (order by latency_ms)::numeric)  as p50_ms,
       round(percentile_cont(0.95) within group (order by latency_ms)::numeric) as p95_ms,
       max(latency_ms)                                                       as max_ms,
       count(cost_usd)                                                       as priced,
       round(avg(cost_usd), 7)                                               as avg_cost_usd,
       round(sum(cost_usd), 5)                                               as sum_cost_usd,
       round(avg((coalesce(input_tokens, 0) * p.input_usd + coalesce(output_tokens, 0) * p.output_usd) / 1e6), 7) as avg_est_cost_usd
from real
left join price p using (model)
group by call_type, model
order by call_type, model;
