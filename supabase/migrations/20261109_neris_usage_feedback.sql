begin;

create table if not exists public.neris_chat_activity (
    user_id uuid not null references auth.users(id) on delete cascade,
    activity_date date not null,
    last_seen_at timestamptz not null default now(),
    primary key (user_id, activity_date)
);

alter table public.neris_chat_activity enable row level security;
revoke all on public.neris_chat_activity from public, anon, authenticated;
grant all on public.neris_chat_activity to service_role;

create table if not exists public.neris_evolution_feedback (
    user_id uuid primary key references auth.users(id) on delete cascade,
    answer text not null check (answer in ('yes', 'not_sure', 'no')),
    submitted_at timestamptz not null default now()
);

alter table public.neris_evolution_feedback enable row level security;
revoke all on public.neris_evolution_feedback from public, anon, authenticated;
grant all on public.neris_evolution_feedback to service_role;

create or replace function public.record_neris_chat_activity(target_user_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
    if auth.uid() is distinct from target_user_id then
        raise insufficient_privilege using message = 'Cannot record activity for another user';
    end if;

    insert into public.neris_chat_activity (user_id, activity_date, last_seen_at)
    values (target_user_id, (now() at time zone 'UTC')::date, now())
    on conflict (user_id, activity_date)
    do update set last_seen_at = excluded.last_seen_at;

    return true;
end;
$$;

revoke all on function public.record_neris_chat_activity(uuid) from public, anon;
grant execute on function public.record_neris_chat_activity(uuid) to authenticated;

create or replace function public.submit_neris_evolution_feedback(
    target_user_id uuid,
    feedback_answer text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
    if auth.uid() is distinct from target_user_id then
        raise insufficient_privilege using message = 'Cannot submit feedback for another user';
    end if;

    if feedback_answer is null or feedback_answer not in ('yes', 'not_sure', 'no') then
        raise check_violation using message = 'Unsupported Neris evolution feedback answer';
    end if;

    insert into public.neris_evolution_feedback (user_id, answer, submitted_at)
    values (target_user_id, feedback_answer, now())
    on conflict (user_id)
    do update set
        answer = excluded.answer,
        submitted_at = excluded.submitted_at;

    return true;
end;
$$;

revoke all on function public.submit_neris_evolution_feedback(uuid, text) from public, anon;
grant execute on function public.submit_neris_evolution_feedback(uuid, text) to authenticated;

create or replace function public.get_neris_admin_usage_metrics()
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

    select jsonb_build_object(
        'active_users_7d',
        (
            select count(distinct activity.user_id)
              from public.neris_chat_activity as activity
             where activity.activity_date >= (now() at time zone 'UTC')::date - 6
        ),
        'evolution_feedback',
        (
            select jsonb_build_object(
                'yes', count(*) filter (where feedback.answer = 'yes'),
                'not_sure', count(*) filter (where feedback.answer = 'not_sure'),
                'no', count(*) filter (where feedback.answer = 'no'),
                'responses', count(*)
            )
              from public.neris_evolution_feedback as feedback
        )
    )
      into metrics;

    return metrics;
end;
$$;

revoke all on function public.get_neris_admin_usage_metrics() from public, anon, authenticated;
grant execute on function public.get_neris_admin_usage_metrics() to service_role;

commit;
