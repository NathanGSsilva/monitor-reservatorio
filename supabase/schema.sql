begin;

create table public.readings (
  device_id text not null,
  message_id text not null,
  distance_cm numeric(6, 1) not null check (distance_cm > 0),
  level_pct numeric(4, 1) not null check (level_pct between 0 and 100),
  received_at timestamptz not null default now(),
  primary key (device_id, message_id)
);

create index readings_device_time
  on public.readings (device_id, received_at desc);

alter table public.readings enable row level security;

revoke all on public.readings from anon, authenticated;
grant select on public.readings to anon, authenticated;
grant select, insert on public.readings to service_role;

create policy "Leitura publica das medicoes simuladas"
  on public.readings
  for select
  to anon, authenticated
  using (true);

commit;