begin;

create table if not exists public.neris_chat_quota_reservations (
    user_id uuid not null references auth.users(id) on delete cascade,
    request_id uuid not null,
    day_started date not null,
    month_started date not null,
    refunded_at timestamptz,
    created_at timestamptz not null default now(),
    primary key (user_id, request_id)
);

alter table public.neris_chat_quota_reservations enable row level security;
revoke all on public.neris_chat_quota_reservations from public, anon, authenticated;
grant all on public.neris_chat_quota_reservations to service_role;

drop function if exists public.consume_neris_chat_quota(uuid);

create function public.consume_neris_chat_quota(
    target_user_id uuid,
    request_id uuid default null
)
returns table (
    allowed boolean,
    daily_remaining integer,
    monthly_remaining integer
)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    user_plan text;
    active_status text;
    account_created_at timestamptz;
    daily_limit integer;
    monthly_limit integer;
    today date := current_date;
    month_start date := date_trunc('month', current_date)::date;
    updated_usage public.neris_chat_usage%rowtype;
begin
    if auth.uid() is distinct from target_user_id then
        raise insufficient_privilege using message = 'Cannot consume quota for another user';
    end if;

    select profile.plano, profile.status_assinatura, account.created_at
      into user_plan, active_status, account_created_at
      from public.usuarios_saas as profile
      join auth.users as account on account.id = profile.id
     where profile.id = target_user_id;

    if user_plan is null or active_status is distinct from 'ativo' then
        return query select false, 0, 0;
        return;
    end if;

    if user_plan = 'Neris 3.5'
       and account_created_at > now() - interval '7 days' then
        user_plan := 'Neris Pro';
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

    if request_id is not null and exists (
        select 1
          from public.neris_chat_quota_reservations as reservation
         where reservation.user_id = target_user_id
           and reservation.request_id = consume_neris_chat_quota.request_id
    ) then
        return query select false, 0, 0;
        return;
    end if;

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

    if not found then
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
        return;
    end if;

    if request_id is not null then
        insert into public.neris_chat_quota_reservations (
            user_id, request_id, day_started, month_started
        )
        values (target_user_id, request_id, today, month_start);
    end if;

    return query select
        true,
        greatest(daily_limit - updated_usage.day_messages, 0),
        greatest(monthly_limit - updated_usage.month_messages, 0);
end;
$$;

revoke all on function public.consume_neris_chat_quota(uuid, uuid) from public, anon;
grant execute on function public.consume_neris_chat_quota(uuid, uuid) to authenticated;

create or replace function public.refund_neris_chat_quota(
    target_user_id uuid,
    request_id uuid
)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    reservation public.neris_chat_quota_reservations%rowtype;
begin
    if auth.uid() is distinct from target_user_id then
        raise insufficient_privilege using message = 'Cannot refund quota for another user';
    end if;

    select *
      into reservation
      from public.neris_chat_quota_reservations as quota_reservation
     where quota_reservation.user_id = target_user_id
       and quota_reservation.request_id = refund_neris_chat_quota.request_id
     for update;

    if not found then
        return false;
    end if;

    if reservation.refunded_at is not null then
        return true;
    end if;

    update public.neris_chat_usage as usage
       set day_messages = case
               when usage.day_started = reservation.day_started
               then greatest(usage.day_messages - 1, 0)
               else usage.day_messages
           end,
           month_messages = case
               when usage.month_started = reservation.month_started
               then greatest(usage.month_messages - 1, 0)
               else usage.month_messages
           end,
           updated_at = now()
     where usage.user_id = target_user_id;

    update public.neris_chat_quota_reservations as quota_reservation
       set refunded_at = now()
     where quota_reservation.user_id = target_user_id
       and quota_reservation.request_id = refund_neris_chat_quota.request_id;

    return true;
end;
$$;

revoke all on function public.refund_neris_chat_quota(uuid, uuid) from public, anon;
grant execute on function public.refund_neris_chat_quota(uuid, uuid) to authenticated;

commit;
