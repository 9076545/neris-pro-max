begin;

create table if not exists public.logs_agentes (
    id bigserial primary key,
    agente_id text not null,
    nome_agente text not null,
    status_acao text not null,
    log_texto text not null,
    created_at timestamptz not null default timezone('utc'::text, now())
);

alter table public.logs_agentes enable row level security;
revoke all on table public.logs_agentes from public, anon, authenticated;
grant all on table public.logs_agentes to service_role;

do $$
declare
    sequence_name text := pg_get_serial_sequence('public.logs_agentes', 'id');
begin
    if sequence_name is not null then
        execute format('grant usage, select on sequence %s to service_role', sequence_name);
    end if;
end
$$;

drop policy if exists "logs_agentes_backend_only"
    on public.logs_agentes;
create policy "logs_agentes_backend_only"
    on public.logs_agentes for all to service_role
    using (true) with check (true);

drop policy if exists "logs_agentes_backend_only_guard"
    on public.logs_agentes;
create policy "logs_agentes_backend_only_guard"
    on public.logs_agentes as restrictive for all to public
    using ((select auth.role()) = 'service_role')
    with check ((select auth.role()) = 'service_role');

notify pgrst, 'reload schema';
commit;
