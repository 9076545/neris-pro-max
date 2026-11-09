begin;

create table if not exists public.neris_brain_activity (
    user_id uuid not null references auth.users(id) on delete cascade,
    brain_id text not null check (brain_id in ('neris', 'gemini', 'claude')),
    activity_date date not null,
    request_count integer not null default 1 check (request_count > 0),
    last_used_at timestamptz not null default now(),
    primary key (user_id, brain_id, activity_date)
);

alter table public.neris_brain_activity enable row level security;
revoke all on public.neris_brain_activity from public, anon, authenticated;
grant all on public.neris_brain_activity to service_role;

create or replace function public.record_neris_brain_activity(
    target_user_id uuid,
    selected_brain text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
    if auth.uid() is distinct from target_user_id then
        raise insufficient_privilege using message = 'Cannot record brain activity for another user';
    end if;

    if selected_brain is null or selected_brain not in ('neris', 'gemini', 'claude') then
        raise check_violation using message = 'Unsupported Neris brain';
    end if;

    insert into public.neris_brain_activity (
        user_id,
        brain_id,
        activity_date,
        request_count,
        last_used_at
    )
    values (
        target_user_id,
        selected_brain,
        (now() at time zone 'UTC')::date,
        1,
        now()
    )
    on conflict (user_id, brain_id, activity_date)
    do update set
        request_count = public.neris_brain_activity.request_count + 1,
        last_used_at = excluded.last_used_at;

    return true;
end;
$$;

revoke all on function public.record_neris_brain_activity(uuid, text) from public, anon;
grant execute on function public.record_neris_brain_activity(uuid, text) to authenticated;

create or replace function public.get_neris_admin_brain_usage_metrics()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    metrics jsonb;
begin
    if coalesce(auth.role(), '') <> 'service_role' then
        raise insufficient_privilege using message = 'Service role is required for aggregate metrics';
    end if;

    select jsonb_object_agg(brains.id, coalesce(activity.request_count, 0))
      into metrics
      from (values ('neris'), ('gemini'), ('claude')) as brains(id)
      left join (
          select activity.brain_id, sum(activity.request_count) as request_count
            from public.neris_brain_activity as activity
           where activity.activity_date >= (now() at time zone 'UTC')::date - 6
           group by activity.brain_id
      ) as activity on activity.brain_id = brains.id;

    return coalesce(metrics, '{}'::jsonb);
end;
$$;

revoke all on function public.get_neris_admin_brain_usage_metrics() from public, anon, authenticated;
grant execute on function public.get_neris_admin_brain_usage_metrics() to service_role;

commit;
