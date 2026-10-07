-- DayOne multi-user schema. Run in Supabase SQL Editor before starting the app.
create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  height_cm numeric(5,1) check (height_cm between 80 and 250),
  favorite_exercise text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id) values (new.id) on conflict (id) do nothing;
  return new;
end;
$$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
for each row execute procedure public.handle_new_user();

create table if not exists public.exercises (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid references auth.users(id) on delete cascade,
  name text not null check (length(trim(name)) > 0),
  muscle_group text not null default 'Other',
  equipment text not null default '',
  created_at timestamptz not null default now()
);
create unique index if not exists exercises_global_name_ci on public.exercises (lower(name)) where owner_id is null;
create unique index if not exists exercises_user_name_ci on public.exercises (owner_id, lower(name)) where owner_id is not null;
create index if not exists exercises_owner_muscle_idx on public.exercises (owner_id, muscle_group);

create table if not exists public.routine_days (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  day text not null check (day in ('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')),
  name text not null default 'Rest',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, day),
  unique (user_id, id)
);
create index if not exists routine_days_user_idx on public.routine_days (user_id);

create table if not exists public.routine_exercises (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  routine_day_id uuid not null,
  position integer not null check (position >= 0),
  exercise_name text not null,
  sets integer not null check (sets between 1 and 20),
  reps integer not null check (reps between 1 and 500),
  created_at timestamptz not null default now(),
  foreign key (user_id, routine_day_id) references public.routine_days(user_id, id) on delete cascade,
  unique (routine_day_id, position)
);
create index if not exists routine_exercises_day_idx on public.routine_exercises (user_id, routine_day_id, position);

create table if not exists public.workout_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null default current_date,
  day text not null check (day in ('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')),
  request_key uuid not null,
  legacy_key text,
  created_at timestamptz not null default now(),
  unique (user_id, request_key),
  unique (user_id, id)
);
create unique index if not exists workout_sessions_legacy_key_idx on public.workout_sessions(user_id, legacy_key) where legacy_key is not null;
create index if not exists workout_sessions_user_date_idx on public.workout_sessions(user_id, date desc, created_at desc);

create table if not exists public.session_exercises (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  session_id uuid not null,
  position integer not null check (position >= 0),
  exercise_name text not null,
  muscle_group text not null default 'Other',
  sets integer not null check (sets between 1 and 50),
  reps integer not null check (reps between 1 and 500),
  weight numeric(8,2) not null default 0 check (weight >= 0),
  created_at timestamptz not null default now(),
  foreign key (user_id, session_id) references public.workout_sessions(user_id, id) on delete cascade,
  unique (session_id, position)
);
create index if not exists session_exercises_session_idx on public.session_exercises (user_id, session_id, position);
create index if not exists session_exercises_name_idx on public.session_exercises (user_id, lower(exercise_name));

create table if not exists public.body_weight_entries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  weight numeric(7,2) not null check (weight > 0),
  created_at timestamptz not null default now(),
  unique (user_id, date)
);
create index if not exists body_weight_user_date_idx on public.body_weight_entries (user_id, date);

create table if not exists public.calorie_entries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  calories integer not null check (calories between 0 and 20000),
  created_at timestamptz not null default now(),
  unique (user_id, date)
);
create index if not exists calorie_user_date_idx on public.calorie_entries (user_id, date desc);

create table if not exists public.legacy_imports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  source_key text not null,
  imported_at timestamptz not null default now(),
  unique (user_id, source_key)
);

-- Atomic replacement of a day's plan, so an insert failure cannot erase its old exercises.
create or replace function public.save_routine_day(p_day text, p_name text, p_exercises jsonb)
returns uuid language plpgsql set search_path = '' as $$
declare v_user uuid := auth.uid(); v_day_id uuid; v_item jsonb; v_position integer := 0;
begin
  if v_user is null then raise exception 'Authentication required'; end if;
  insert into public.routine_days(user_id, day, name) values (v_user, p_day, p_name)
  on conflict (user_id, day) do update set name = excluded.name, updated_at = now()
  returning id into v_day_id;
  delete from public.routine_exercises where user_id = v_user and routine_day_id = v_day_id;
  for v_item in select value from jsonb_array_elements(coalesce(p_exercises, '[]'::jsonb)) loop
    insert into public.routine_exercises(user_id, routine_day_id, position, exercise_name, sets, reps)
    values (v_user, v_day_id, v_position, v_item->>'exercise', (v_item->>'sets')::integer, (v_item->>'reps')::integer);
    v_position := v_position + 1;
  end loop;
  return v_day_id;
end;
$$;

-- The caller-supplied key makes a repeated form submission idempotent.
create or replace function public.log_workout_session(p_day text, p_request_key uuid, p_entries jsonb)
returns uuid language plpgsql set search_path = '' as $$
declare v_user uuid := auth.uid(); v_session_id uuid; v_item jsonb; v_position integer := 0;
begin
  if v_user is null then raise exception 'Authentication required'; end if;
  select id into v_session_id from public.workout_sessions where user_id = v_user and request_key = p_request_key;
  if v_session_id is not null then return v_session_id; end if;
  insert into public.workout_sessions(user_id, date, day, request_key)
  values (v_user, current_date, p_day, p_request_key) returning id into v_session_id;
  for v_item in select value from jsonb_array_elements(coalesce(p_entries, '[]'::jsonb)) loop
    insert into public.session_exercises(user_id, session_id, position, exercise_name, muscle_group, sets, reps, weight)
    values (v_user, v_session_id, v_position, v_item->>'exercise', coalesce(v_item->>'muscle_group','Other'),
            (v_item->>'sets')::integer, (v_item->>'reps')::integer, (v_item->>'weight')::numeric);
    v_position := v_position + 1;
  end loop;
  return v_session_id;
end;
$$;

create or replace function public.update_workout_session(p_session_id uuid, p_day text, p_entries jsonb)
returns void language plpgsql set search_path = '' as $$
declare v_user uuid := auth.uid(); v_item jsonb; v_position integer := 0;
begin
  if v_user is null then raise exception 'Authentication required'; end if;
  update public.workout_sessions set day = p_day where id = p_session_id and user_id = v_user;
  if not found then raise exception 'Workout session not found'; end if;
  delete from public.session_exercises where session_id = p_session_id and user_id = v_user;
  for v_item in select value from jsonb_array_elements(coalesce(p_entries, '[]'::jsonb)) loop
    insert into public.session_exercises(user_id, session_id, position, exercise_name, muscle_group, sets, reps, weight)
    values (v_user, p_session_id, v_position, v_item->>'exercise', coalesce(v_item->>'muscle_group','Other'),
            (v_item->>'sets')::integer, (v_item->>'reps')::integer, (v_item->>'weight')::numeric);
    v_position := v_position + 1;
  end loop;
end;
$$;

revoke all on function public.save_routine_day(text,text,jsonb) from public, anon;
revoke all on function public.log_workout_session(text,uuid,jsonb) from public, anon;
revoke all on function public.update_workout_session(uuid,text,jsonb) from public, anon;
grant execute on function public.save_routine_day(text,text,jsonb) to authenticated;
grant execute on function public.log_workout_session(text,uuid,jsonb) to authenticated;
grant execute on function public.update_workout_session(uuid,text,jsonb) to authenticated;

alter table public.profiles enable row level security;
alter table public.exercises enable row level security;
alter table public.routine_days enable row level security;
alter table public.routine_exercises enable row level security;
alter table public.workout_sessions enable row level security;
alter table public.session_exercises enable row level security;
alter table public.body_weight_entries enable row level security;
alter table public.calorie_entries enable row level security;
alter table public.legacy_imports enable row level security;

drop policy if exists "profiles own rows" on public.profiles;
create policy "profiles own rows" on public.profiles for all to authenticated
using (id = (select auth.uid())) with check (id = (select auth.uid()));

drop policy if exists "read shared and own exercises" on public.exercises;
create policy "read shared and own exercises" on public.exercises for select to authenticated
using (owner_id is null or owner_id = (select auth.uid()));
drop policy if exists "insert own exercises" on public.exercises;
create policy "insert own exercises" on public.exercises for insert to authenticated
with check (owner_id = (select auth.uid()));
drop policy if exists "update own exercises" on public.exercises;
create policy "update own exercises" on public.exercises for update to authenticated
using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));
drop policy if exists "delete own exercises" on public.exercises;
create policy "delete own exercises" on public.exercises for delete to authenticated
using (owner_id = (select auth.uid()));

do $$
declare t text;
begin
  foreach t in array array['routine_days','routine_exercises','workout_sessions','session_exercises','body_weight_entries','calorie_entries','legacy_imports'] loop
    execute format('drop policy if exists %I on public.%I', t || ' own rows', t);
    execute format('create policy %I on public.%I for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()))', t || ' own rows', t);
  end loop;
end $$;

grant usage on schema public to authenticated;
grant select, insert, update, delete on public.profiles, public.exercises, public.routine_days,
  public.routine_exercises, public.workout_sessions, public.session_exercises,
  public.body_weight_entries, public.calorie_entries, public.legacy_imports to authenticated;
