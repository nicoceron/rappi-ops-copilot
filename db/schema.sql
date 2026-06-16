create extension if not exists pgcrypto;

create table if not exists dim_zone (
  zone_id text primary key,
  country text not null,
  city text not null,
  zone text not null,
  zone_type text,
  zone_prioritization text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists semantic_metric (
  metric_key text primary key,
  metric_name text not null unique,
  source text not null,
  default_direction text not null check (
    default_direction in ('higher_better', 'lower_better', 'unknown')
  ),
  value_kind text not null check (
    value_kind in ('rate', 'currency_per_order', 'count', 'index', 'unknown')
  ),
  outlier_policy text not null default 'none',
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists metric_synonym (
  synonym text primary key,
  metric_key text not null references semantic_metric(metric_key) on delete cascade
);

create table if not exists fact_metric_week (
  zone_id text not null references dim_zone(zone_id) on delete cascade,
  metric_key text not null references semantic_metric(metric_key) on delete cascade,
  week_offset int not null check (week_offset between 0 and 8),
  week_label text not null,
  value numeric not null,
  source_column text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (zone_id, metric_key, week_offset)
);

create table if not exists fact_orders_week (
  zone_id text not null references dim_zone(zone_id) on delete cascade,
  week_offset int not null check (week_offset between 0 and 8),
  week_label text not null,
  orders numeric not null,
  source_column text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (zone_id, week_offset)
);

create table if not exists query_audit (
  query_id uuid primary key default gen_random_uuid(),
  session_id text,
  user_question text not null,
  semantic_request jsonb not null,
  sql_text text,
  row_count int,
  created_at timestamptz not null default now()
);

create table if not exists executive_insight_report (
  report_id uuid primary key default gen_random_uuid(),
  source text not null,
  period_label text not null,
  report_markdown text not null,
  report_json jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_dim_zone_country_city_zone
  on dim_zone (country, city, zone);

create index if not exists idx_fact_metric_metric_week
  on fact_metric_week (metric_key, week_offset);

create index if not exists idx_fact_metric_zone
  on fact_metric_week (zone_id);

create index if not exists idx_fact_orders_week
  on fact_orders_week (week_offset);

create index if not exists idx_executive_insight_report_created_at
  on executive_insight_report (created_at desc);
