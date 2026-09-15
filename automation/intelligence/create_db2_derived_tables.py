"""Create derived analytical tables in DB2 for migrated/generated data."""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

DDL = """
CREATE TABLE IF NOT EXISTS public.work_analysis (
    work_id bigint PRIMARY KEY,
    member_id bigint,
    member_type text,
    constituency_id bigint,
    state_id bigint,
    state_name text,
    work_category text,
    activity_name text,
    normalized_activity text,
    work_description text,
    status text,
    recommended_amount numeric,
    sanction_amount numeric,
    expenditure_amount numeric,
    completion_amount numeric,
    recommendation_date date,
    sanction_date date,
    first_expenditure_date date,
    last_expenditure_date date,
    completion_date date,
    sanction_delay_days integer,
    project_age_days integer,
    execution_days integer,
    pending_days integer,
    expenditure_percentage numeric,
    completion_percentage numeric,
    benchmark_peer_group text,
    benchmark_quality text,
    benchmark_sample_size bigint,
    cost_p25 double precision,
    cost_p50 double precision,
    cost_p75 double precision,
    cost_p90 double precision,
    cost_p95 double precision,
    duration_p25 double precision,
    duration_p50 double precision,
    duration_p75 double precision,
    duration_p90 double precision,
    duration_p95 double precision,
    cost_percentile numeric,
    duration_percentile numeric,
    cost_status text,
    duration_status text,
    cost_deviation_from_median_percentage numeric,
    duration_deviation_from_median_percentage numeric,
    risk_flags text[],
    flag_count integer,
    risk_level text,
    last_calculated timestamp with time zone,
    delay_probability numeric,
    delay_risk_band text,
    isolation_score numeric,
    isolation_level text
);

CREATE TABLE IF NOT EXISTS public.mla_work_analysis (
    work_id bigint PRIMARY KEY,
    member_id bigint,
    member_type text,
    constituency_id bigint,
    state_id bigint,
    state_name text,
    work_category text,
    activity_name text,
    normalized_activity text,
    work_description text,
    status text,
    recommended_amount numeric,
    sanction_amount numeric,
    expenditure_amount numeric,
    completion_amount numeric,
    recommendation_date date,
    sanction_date date,
    first_expenditure_date date,
    last_expenditure_date date,
    completion_date date,
    sanction_delay_days integer,
    project_age_days integer,
    execution_days integer,
    pending_days integer,
    expenditure_percentage numeric,
    completion_percentage numeric,
    benchmark_peer_group text,
    benchmark_quality text,
    benchmark_sample_size bigint,
    cost_p25 double precision,
    cost_p50 double precision,
    cost_p75 double precision,
    cost_p90 double precision,
    cost_p95 double precision,
    duration_p25 double precision,
    duration_p50 double precision,
    duration_p75 double precision,
    duration_p90 double precision,
    duration_p95 double precision,
    cost_percentile numeric,
    duration_percentile numeric,
    cost_status text,
    duration_status text,
    cost_deviation_from_median_percentage numeric,
    duration_deviation_from_median_percentage numeric,
    risk_flags text[],
    flag_count integer,
    risk_level text,
    last_calculated timestamp with time zone,
    delay_probability numeric,
    delay_risk_band text,
    isolation_score numeric,
    isolation_level text
);

CREATE TABLE IF NOT EXISTS public.ml_work_anomaly (
    member_type text,
    work_id bigint,
    ml_anomaly_score double precision,
    ml_anomaly_flag boolean,
    model_name text,
    model_version text,
    feature_version text,
    calculated_at timestamp with time zone,
    PRIMARY KEY (member_type, work_id)
);

CREATE TABLE IF NOT EXISTS public.category_metrics (
    scope text,
    state_id bigint,
    category text,
    sample_size bigint,
    distinct_states bigint,
    distinct_members bigint,
    completed_works bigint,
    ongoing_works bigint,
    recommended_works bigint,
    sanctioned_works bigint,
    recommended_amount numeric,
    sanctioned_amount numeric,
    expenditure_amount numeric,
    completion_rate_pct numeric,
    sanction_rate_pct numeric,
    utilization_pct numeric,
    avg_work_cost numeric,
    median_work_cost numeric,
    avg_execution_days numeric,
    median_execution_days numeric,
    overdue_rate_pct numeric,
    risk_rate_pct numeric,
    cost_anomaly_rate_pct numeric,
    duration_anomaly_rate_pct numeric,
    confidence text,
    PRIMARY KEY (scope, state_id, category)
);

ALTER TABLE public.member_metrics
    ADD COLUMN IF NOT EXISTS cluster_id integer,
    ADD COLUMN IF NOT EXISTS cluster_label text,
    ADD COLUMN IF NOT EXISTS risk_score numeric,
    ADD COLUMN IF NOT EXISTS risk_level text,
    ADD COLUMN IF NOT EXISTS risk_confidence text,
    ADD COLUMN IF NOT EXISTS risk_evidence jsonb,
    ADD COLUMN IF NOT EXISTS sample_size integer;

ALTER TABLE public.state_metrics
    ADD COLUMN IF NOT EXISTS cluster_id integer,
    ADD COLUMN IF NOT EXISTS cluster_label text,
    ADD COLUMN IF NOT EXISTS risk_score numeric,
    ADD COLUMN IF NOT EXISTS risk_level text,
    ADD COLUMN IF NOT EXISTS risk_confidence text,
    ADD COLUMN IF NOT EXISTS risk_evidence jsonb,
    ADD COLUMN IF NOT EXISTS sample_size integer;

CREATE TABLE IF NOT EXISTS public.fy_metrics (
    fy_start integer,
    fy_label text,
    member_type text,
    recommended_works bigint,
    sanctioned_works bigint,
    completed_works bigint,
    expenditure_count bigint,
    recommended_amount numeric,
    sanctioned_amount numeric,
    completion_amount numeric,
    expenditure_amount numeric,
    PRIMARY KEY (fy_start, member_type)
);
"""


async def main():
    db2 = await asyncpg.connect(dsn=os.environ["DB2_DATABASE_URL"])
    try:
        await db2.execute(DDL)
        print("DB2 derived tables created/verified.")
    finally:
        await db2.close()


if __name__ == "__main__":
    asyncio.run(main())
