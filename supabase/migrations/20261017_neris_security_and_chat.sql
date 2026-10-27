begin;

alter table public.usuarios_saas
    add column if not exists historico_chat jsonb not null default '[]'::jsonb;

create table if not exists public.mensagens_whatsapp (
    id bigserial primary key,
    direcao text not null check (direcao in ('inbound', 'outbound')),
    contato_whatsapp text not null,
    mensagem text not null,
    meta_message_id text,
    created_at timestamptz not null default timezone('utc'::text, now())
);

create table if not exists public.inventario_shopify (
    product_gid text primary key,
    titulo text not null,
    status text not null,
    total_inventory integer not null,
    sincronizado_em timestamptz not null default timezone('utc'::text, now())
);

alter table public.usuarios_saas enable row level security;
alter table public.memoria_ia enable row level security;
alter table public.logs_agentes enable row level security;
alter table public.leads_prospeccao enable row level security;
alter table public.leads_prospeccao
    add column if not exists consentimento_contato boolean not null default false,
    add column if not exists consentimento_em timestamptz,
    add column if not exists owner_user_id uuid references auth.users(id) on delete cascade;

update public.usuarios_saas
   set plano = case plano
       when 'Neris Lite' then 'Neris 3.5'
       when 'Neris Advanced' then 'Neris Pro'
       when 'Neris Ultra Quantum' then 'Neris Ultra Max'
       else plano
   end
 where plano in ('Neris Lite', 'Neris Advanced', 'Neris Ultra Quantum');

alter table public.usuarios_saas
    alter column plano set default 'Neris 3.5';
alter table public.mensagens_whatsapp enable row level security;
alter table public.inventario_shopify enable row level security;

create policy "usuarios_saas_select_self"
    on public.usuarios_saas for select to authenticated
    using (id = (select auth.uid()));

create policy "usuarios_saas_update_self"
    on public.usuarios_saas for update to authenticated
    using (id = (select auth.uid()))
    with check (id = (select auth.uid()));

revoke update on public.usuarios_saas from anon, authenticated;
grant update (nome, email) on public.usuarios_saas to authenticated;

create policy "memoria_ia_backend_only"
    on public.memoria_ia for all to service_role
    using (true) with check (true);

create policy "logs_agentes_backend_only"
    on public.logs_agentes for all to service_role
    using (true) with check (true);

create policy "logs_agentes_backend_only_guard"
    on public.logs_agentes as restrictive for all to public
    using ((select auth.role()) = 'service_role')
    with check ((select auth.role()) = 'service_role');

create policy "leads_prospeccao_backend_only"
    on public.leads_prospeccao for all to service_role
    using (true) with check (true);

create policy "leads_prospeccao_backend_only_guard"
    on public.leads_prospeccao as restrictive for all to public
    using ((select auth.role()) = 'service_role')
    with check ((select auth.role()) = 'service_role');

create policy "mensagens_whatsapp_backend_only"
    on public.mensagens_whatsapp for all to service_role
    using (true) with check (true);

create policy "inventario_shopify_backend_only"
    on public.inventario_shopify for all to service_role
    using (true) with check (true);

create or replace function public.append_neris_chat_turn(
    target_user_id uuid,
    chat_turn jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    updated_history jsonb;
begin
    if auth.uid() is distinct from target_user_id then
        raise insufficient_privilege using message = 'Cannot update another user history';
    end if;
    if jsonb_typeof(chat_turn) <> 'object' then
        raise invalid_parameter_value using message = 'chat_turn must be a JSON object';
    end if;
    if jsonb_typeof(chat_turn -> 'user_text') is distinct from 'string'
       or jsonb_typeof(chat_turn -> 'assistant_text') is distinct from 'string'
       or length(chat_turn ->> 'user_text') not between 1 and 20000
       or length(chat_turn ->> 'assistant_text') not between 1 and 10000
       or pg_column_size(chat_turn) > 32768 then
        raise invalid_parameter_value using message = 'chat_turn fields are invalid';
    end if;

    update public.usuarios_saas
       set historico_chat = (
           select coalesce(
               jsonb_agg(history.item order by history.ordinality),
               '[]'::jsonb
           )
           from jsonb_array_elements(coalesce(usuarios_saas.historico_chat, '[]'::jsonb))
                with ordinality as history(item, ordinality)
           where history.ordinality > greatest(
               jsonb_array_length(coalesce(usuarios_saas.historico_chat, '[]'::jsonb)) - 49,
               0
           )
       ) || jsonb_build_array(chat_turn)
     where usuarios_saas.id = target_user_id
    returning historico_chat into updated_history;

    if updated_history is null then
        raise no_data_found using message = 'SaaS user profile not found';
    end if;
    return updated_history;
end;
$$;

revoke all on function public.append_neris_chat_turn(uuid, jsonb) from public, anon;
grant execute on function public.append_neris_chat_turn(uuid, jsonb) to authenticated;

create or replace function public.match_memoria_ia(
    query_embedding vector(1536),
    match_count integer default 5,
    filter_context text default null
)
returns table (
    id bigint,
    contexto text,
    conteudo text,
    similarity double precision
)
language sql
stable
security invoker
set search_path = public
as $$
    select
        memory.id,
        memory.contexto,
        memory.conteudo,
        1 - (memory.vetor_embedding <=> query_embedding) as similarity
    from public.memoria_ia as memory
    where memory.vetor_embedding is not null
      and (filter_context is null or memory.contexto = filter_context)
    order by memory.vetor_embedding <=> query_embedding
    limit greatest(1, least(match_count, 50));
$$;

revoke all on function public.match_memoria_ia(vector, integer, text) from public, anon, authenticated;
grant execute on function public.match_memoria_ia(vector, integer, text) to service_role;

create table if not exists public.neris_chat_usage (
    user_id uuid primary key references auth.users(id) on delete cascade,
    day_started date not null,
    day_messages integer not null default 0,
    month_started date not null,
    month_messages integer not null default 0,
    updated_at timestamptz not null default now(),
    check (day_messages >= 0),
    check (month_messages >= 0)
);
alter table public.neris_chat_usage enable row level security;
revoke all on public.neris_chat_usage from anon, authenticated;
grant all on public.neris_chat_usage to service_role;

create or replace function public.consume_neris_chat_quota(target_user_id uuid)
returns table (allowed boolean, daily_remaining integer, monthly_remaining integer)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    user_plan text;
    active_status text;
    daily_limit integer;
    monthly_limit integer;
    today date := current_date;
    month_start date := date_trunc('month', current_date)::date;
    updated_usage public.neris_chat_usage%rowtype;
begin
    if auth.uid() is distinct from target_user_id then
        raise insufficient_privilege using message = 'Cannot consume quota for another user';
    end if;

    select profile.plano, profile.status_assinatura
      into user_plan, active_status
      from public.usuarios_saas as profile
     where profile.id = target_user_id;

    if user_plan is null or active_status is distinct from 'ativo' then
        return query select false, 0, 0;
        return;
    end if;

    case user_plan
        when 'Neris 3.5' then daily_limit := 50; monthly_limit := 1000;
        when 'Neris Pro' then daily_limit := 300; monthly_limit := 10000;
        when 'Neris 5.6' then daily_limit := 1000; monthly_limit := 30000;
        when 'Neris Ultra Max' then daily_limit := 3333; monthly_limit := 100000;
        else
            return query select false, 0, 0;
            return;
    end case;

    insert into public.neris_chat_usage as usage (
        user_id, day_started, day_messages, month_started, month_messages, updated_at
    )
    values (target_user_id, today, 1, month_start, 1, now())
    on conflict (user_id) do update
       set day_messages = case
               when usage.day_started = today then usage.day_messages + 1 else 1
           end,
           day_started = today,
           month_messages = case
               when usage.month_started = month_start then usage.month_messages + 1 else 1
           end,
           month_started = month_start,
           updated_at = now()
     where (usage.day_started <> today or usage.day_messages < daily_limit)
       and (usage.month_started <> month_start or usage.month_messages < monthly_limit)
    returning usage.* into updated_usage;

    if found then
        return query select
            true,
            greatest(daily_limit - updated_usage.day_messages, 0),
            greatest(monthly_limit - updated_usage.month_messages, 0);
        return;
    end if;

    select usage.* into updated_usage
      from public.neris_chat_usage as usage
     where usage.user_id = target_user_id;
    return query select
        false,
        greatest(
            daily_limit - case when updated_usage.day_started = today then updated_usage.day_messages else 0 end,
            0
        ),
        greatest(
            monthly_limit - case when updated_usage.month_started = month_start then updated_usage.month_messages else 0 end,
            0
        );
end;
$$;
revoke all on function public.consume_neris_chat_quota(uuid) from public, anon;
grant execute on function public.consume_neris_chat_quota(uuid) to authenticated;

create table if not exists public.neris_voice_usage (
    user_id uuid primary key references auth.users(id) on delete cascade,
    day_started date not null,
    day_requests integer not null default 0,
    month_started date not null,
    month_requests integer not null default 0,
    updated_at timestamptz not null default now(),
    check (day_requests >= 0),
    check (month_requests >= 0)
);
alter table public.neris_voice_usage enable row level security;
revoke all on public.neris_voice_usage from anon, authenticated;
grant all on public.neris_voice_usage to service_role;

create or replace function public.consume_neris_voice_quota(target_user_id uuid)
returns table (allowed boolean, daily_remaining integer, monthly_remaining integer)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    user_plan text;
    active_status text;
    daily_limit integer;
    monthly_limit integer;
    today date := current_date;
    month_start date := date_trunc('month', current_date)::date;
    updated_usage public.neris_voice_usage%rowtype;
begin
    if auth.uid() is distinct from target_user_id then
        raise insufficient_privilege using message = 'Cannot consume voice quota for another user';
    end if;

    select profile.plano, profile.status_assinatura
      into user_plan, active_status
      from public.usuarios_saas as profile
     where profile.id = target_user_id;

    if user_plan is null or active_status is distinct from 'ativo' then
        return query select false, 0, 0;
        return;
    end if;

    case user_plan
        when 'Neris Pro' then daily_limit := 100; monthly_limit := 2000;
        when 'Neris 5.6' then daily_limit := 300; monthly_limit := 6000;
        when 'Neris Ultra Max' then daily_limit := 1000; monthly_limit := 20000;
        else
            return query select false, 0, 0;
            return;
    end case;

    insert into public.neris_voice_usage as usage (
        user_id, day_started, day_requests, month_started, month_requests, updated_at
    )
    values (target_user_id, today, 1, month_start, 1, now())
    on conflict (user_id) do update
       set day_requests = case
               when usage.day_started = today then usage.day_requests + 1 else 1
           end,
           day_started = today,
           month_requests = case
               when usage.month_started = month_start then usage.month_requests + 1 else 1
           end,
           month_started = month_start,
           updated_at = now()
     where (usage.day_started <> today or usage.day_requests < daily_limit)
       and (usage.month_started <> month_start or usage.month_requests < monthly_limit)
    returning usage.* into updated_usage;

    if found then
        return query select
            true,
            greatest(daily_limit - updated_usage.day_requests, 0),
            greatest(monthly_limit - updated_usage.month_requests, 0);
        return;
    end if;

    select usage.* into updated_usage
      from public.neris_voice_usage as usage
     where usage.user_id = target_user_id;
    return query select
        false,
        greatest(
            daily_limit - case when updated_usage.day_started = today then updated_usage.day_requests else 0 end,
            0
        ),
        greatest(
            monthly_limit - case when updated_usage.month_started = month_start then updated_usage.month_requests else 0 end,
            0
        );
end;
$$;
revoke all on function public.consume_neris_voice_quota(uuid) from public, anon;
grant execute on function public.consume_neris_voice_quota(uuid) to authenticated;

commit;
