-- =====================================================================
-- BOLL BILL  -  Supabase / Postgres schema
-- Run this whole file once in: Supabase Dashboard -> SQL Editor -> New query
-- Safe to re-run: tables use "if not exists", functions use "create or replace".
-- =====================================================================

-- ---------- 1. Tables ------------------------------------------------

create table if not exists public.shops (
  id              uuid primary key default gen_random_uuid(),
  owner_id        uuid not null unique references auth.users(id) on delete cascade,
  name            text not null default 'My Shop' check (char_length(name) between 1 and 120),
  upi_id          text not null default ''
                  check (upi_id = '' or upi_id ~ '^[A-Za-z0-9._-]{2,}@[A-Za-z0-9_]{2,}$'),
  gstin           text not null default ''
                  check (gstin = '' or gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'),
  low_stock_limit int  not null default 5 check (low_stock_limit >= 0),
  next_bill_no    int  not null default 1 check (next_bill_no >= 1),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create table if not exists public.items (
  id          uuid primary key default gen_random_uuid(),
  shop_id     uuid not null references public.shops(id) on delete cascade,
  position    int  not null default 0,
  name        text not null check (char_length(name) between 1 and 120),
  aliases     text[] not null default '{}',
  unit        text not null default 'piece',
  price       numeric(12,2) not null default 0 check (price >= 0),
  stock       numeric(12,2) check (stock is null or stock >= 0),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (shop_id, name)
);

create table if not exists public.bills (
  id         uuid primary key default gen_random_uuid(),
  shop_id    uuid not null references public.shops(id) on delete cascade,
  client_id  uuid,
  bill_no    int  not null,
  billed_at  timestamptz not null default now(),
  sub        numeric(12,2) not null,
  disc_type  text not null default 'pct' check (disc_type in ('pct','amt')),
  disc_val   numeric(12,2) not null default 0,
  disc       numeric(12,2) not null default 0,
  gst_pct    numeric(5,2)  not null default 0,
  gst        numeric(12,2) not null default 0,
  total      numeric(12,2) not null,
  pay_method text not null check (pay_method in ('Cash','UPI','Udhaar')),
  customer   text not null default '',
  paid       boolean not null,
  paid_at    timestamptz,
  lines      jsonb not null default '[]',
  source     text not null default 'app' check (source in ('app','agent')),
  unique (shop_id, bill_no),
  unique (shop_id, client_id)
);
create index if not exists bills_shop_time_idx on public.bills (shop_id, billed_at desc);
create index if not exists bills_udhaar_idx    on public.bills (shop_id, customer)
  where pay_method = 'Udhaar' and not paid;

create table if not exists public.agent_runs (
  id            uuid primary key default gen_random_uuid(),
  shop_id       uuid not null references public.shops(id) on delete cascade,
  user_id       uuid not null,
  kind          text not null,
  input         text not null default '',
  output        text not null default '',
  tool_calls    jsonb not null default '[]',
  model         text,
  input_tokens  int,
  output_tokens int,
  status        text not null default 'ok',
  error         text,
  created_at    timestamptz not null default now()
);
create index if not exists agent_runs_shop_idx on public.agent_runs (shop_id, created_at desc);

create table if not exists public.agent_actions (
  id         uuid primary key default gen_random_uuid(),
  shop_id    uuid not null references public.shops(id) on delete cascade,
  run_id     uuid references public.agent_runs(id) on delete set null,
  kind       text not null check (kind in ('mark_paid')),
  params     jsonb not null default '{}',
  summary    text not null,
  status     text not null default 'pending' check (status in ('pending','confirmed','rejected','expired','failed')),
  result     text,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now() + interval '30 minutes',
  decided_at timestamptz
);
create index if not exists agent_actions_shop_idx on public.agent_actions (shop_id, status, created_at desc);

-- ---------- 2. Helpers ----------------------------------------------

create or replace function public.touch_updated_at() returns trigger
language plpgsql as $$ begin new.updated_at := now(); return new; end $$;

drop trigger if exists shops_touch on public.shops;
create trigger shops_touch before update on public.shops
  for each row execute function public.touch_updated_at();
drop trigger if exists items_touch on public.items;
create trigger items_touch before update on public.items
  for each row execute function public.touch_updated_at();

create or replace function public.my_shop_id() returns uuid
language sql stable security definer set search_path = public as $$
  select id from public.shops where owner_id = auth.uid()
$$;
revoke all on function public.my_shop_id() from public, anon;
grant execute on function public.my_shop_id() to authenticated;

-- ---------- 3. Row Level Security -----------------------------------

alter table public.shops         enable row level security;
alter table public.items         enable row level security;
alter table public.bills         enable row level security;
alter table public.agent_runs    enable row level security;
alter table public.agent_actions enable row level security;

drop policy if exists shops_own on public.shops;
create policy shops_own on public.shops for all to authenticated
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());

drop policy if exists items_own on public.items;
create policy items_own on public.items for all to authenticated
  using (shop_id = public.my_shop_id()) with check (shop_id = public.my_shop_id());

drop policy if exists bills_own on public.bills;
create policy bills_own on public.bills for all to authenticated
  using (shop_id = public.my_shop_id()) with check (shop_id = public.my_shop_id());

drop policy if exists agent_runs_own on public.agent_runs;
create policy agent_runs_own on public.agent_runs for select to authenticated
  using (shop_id = public.my_shop_id());
drop policy if exists agent_runs_insert on public.agent_runs;
create policy agent_runs_insert on public.agent_runs for insert to authenticated
  with check (shop_id = public.my_shop_id() and user_id = auth.uid());

drop policy if exists agent_runs_update on public.agent_runs;
create policy agent_runs_update on public.agent_runs for update to authenticated
  using (shop_id = public.my_shop_id()) with check (shop_id = public.my_shop_id());

drop policy if exists agent_actions_own on public.agent_actions;
create policy agent_actions_own on public.agent_actions for all to authenticated
  using (shop_id = public.my_shop_id()) with check (shop_id = public.my_shop_id());

-- ---------- 4. Views ------------------------------------------------

create or replace view public.udhaar_summary with (security_invoker = true) as
  select shop_id, customer, count(*)::int as bills, sum(total) as due, min(billed_at) as oldest
  from public.bills
  where pay_method = 'Udhaar' and not paid
  group by shop_id, customer;

create or replace view public.bill_lines_v with (security_invoker = true) as
  select b.shop_id, b.id as bill_id, b.bill_no, b.billed_at, b.pay_method, b.customer,
         l->>'name'                  as item,
         l->>'unit'                  as unit,
         (l->>'qty')::numeric        as qty,
         (l->>'price')::numeric      as price,
         round((l->>'qty')::numeric * (l->>'price')::numeric, 2) as amount
  from public.bills b, jsonb_array_elements(b.lines) l;

-- ---------- 5. Functions (security invoker: RLS still applies) -------

create or replace function public.calc_totals(
  p_lines jsonb, p_disc_type text, p_disc_val numeric, p_gst_pct numeric
) returns jsonb language plpgsql immutable as $$
declare sub numeric; dv numeric; disc numeric; taxable numeric; g numeric; gst numeric;
begin
  select coalesce(sum(round((l->>'qty')::numeric * (l->>'price')::numeric, 2)), 0)
    into sub from jsonb_array_elements(p_lines) l;
  dv := greatest(0, coalesce(p_disc_val, 0));
  if p_disc_type = 'pct' then
    dv   := least(dv, 100);
    disc := least(sub, round(sub * dv / 100, 2));
  else
    disc := least(sub, round(dv, 2));
  end if;
  taxable := round(sub - disc, 2);
  g   := least(100, greatest(0, coalesce(p_gst_pct, 0)));
  gst := round(taxable * g / 100, 2);
  return jsonb_build_object('sub', sub, 'disc_type', p_disc_type, 'disc_val', dv, 'disc', disc,
                            'taxable', taxable, 'gst_pct', g, 'gst', gst, 'total', round(taxable + gst, 2));
end $$;

create or replace function public.save_shop(
  p_name text, p_upi text default '', p_gstin text default '', p_low_stock int default null
) returns public.shops language plpgsql security definer set search_path = public as $$
declare r public.shops;
begin
  if auth.uid() is null then raise exception 'login required'; end if;
  insert into public.shops (owner_id, name, upi_id, gstin, low_stock_limit)
  values (auth.uid(), coalesce(nullif(trim(p_name), ''), 'My Shop'), coalesce(trim(p_upi), ''),
          upper(coalesce(trim(p_gstin), '')), coalesce(p_low_stock, 5))
  on conflict (owner_id) do update set
    name            = excluded.name,
    upi_id          = excluded.upi_id,
    gstin           = excluded.gstin,
    low_stock_limit = coalesce(p_low_stock, public.shops.low_stock_limit)
  returning * into r;
  return r;
end $$;

create or replace function public.replace_items(p_items jsonb) returns void
language plpgsql security invoker set search_path = public as $$
declare s uuid := public.my_shop_id();
begin
  if s is null then raise exception 'shop not set up'; end if;
  if jsonb_typeof(p_items) <> 'array' then raise exception 'items must be a list'; end if;

  with src as (
    select distinct on (trim(x->>'name'))
           trim(x->>'name') as name, i::int as pos,
           case when jsonb_typeof(x->'aliases') = 'array'
                then array(select jsonb_array_elements_text(x->'aliases')) else '{}'::text[] end as aliases,
           coalesce(nullif(x->>'unit', ''), 'piece') as unit,
           greatest(0, coalesce((x->>'price')::numeric, 0)) as price,
           greatest(0, (x->>'stock')::numeric) as stock
    from jsonb_array_elements(p_items) with ordinality as t(x, i)
    where trim(coalesce(x->>'name', '')) <> ''
    order by trim(x->>'name'), i
  ), upserted as (
    insert into public.items (shop_id, position, name, aliases, unit, price, stock)
      select s, pos, name, aliases, unit, price, stock from src
    on conflict (shop_id, name) do update set
      position = excluded.position, aliases = excluded.aliases, unit = excluded.unit,
      price = excluded.price, stock = excluded.stock
    returning 1
  )
  delete from public.items it
   where it.shop_id = s and it.name not in (select name from src);
end $$;

create or replace function public.create_bill(
  p_lines        jsonb,
  p_pay          text,
  p_customer     text        default '',
  p_disc_type    text        default 'pct',
  p_disc_val     numeric     default 0,
  p_gst_pct      numeric     default 0,
  p_client_id    uuid        default null,
  p_bill_no      int         default null,
  p_billed_at    timestamptz default null,
  p_source       text        default 'app',
  p_adjust_stock boolean     default true
) returns public.bills language plpgsql security invoker set search_path = public as $$
declare
  s uuid := public.my_shop_id();
  r public.bills; t jsonb; v_no int; v_next int; v_paid boolean; v_at timestamptz; l jsonb;
begin
  if s is null then raise exception 'shop not set up'; end if;

  if p_client_id is not null then
    select * into r from public.bills where shop_id = s and client_id = p_client_id;
    if found then return r; end if;
  end if;

  if jsonb_typeof(p_lines) <> 'array' or jsonb_array_length(p_lines) = 0 then
    raise exception 'bill has no items';
  end if;
  for l in select * from jsonb_array_elements(p_lines) loop
    if coalesce(trim(l->>'name'), '') = '' or coalesce((l->>'qty')::numeric, 0) <= 0
       or coalesce((l->>'price')::numeric, -1) < 0 then
      raise exception 'bad bill line: %', l;
    end if;
  end loop;
  if p_pay not in ('Cash', 'UPI', 'Udhaar') then raise exception 'bad payment method'; end if;
  if p_pay = 'Udhaar' and coalesce(trim(p_customer), '') = '' then
    raise exception 'customer name is required for udhaar';
  end if;
  if p_disc_type not in ('pct', 'amt') then raise exception 'bad discount type'; end if;

  t := public.calc_totals(p_lines, p_disc_type, p_disc_val, p_gst_pct);

  select next_bill_no into v_next from public.shops where id = s for update;
  if p_bill_no is not null and p_bill_no >= 1
     and not exists (select 1 from public.bills where shop_id = s and bill_no = p_bill_no) then
    v_no := p_bill_no;
  else
    v_no := v_next;
  end if;
  update public.shops set next_bill_no = greatest(next_bill_no, v_no + 1) where id = s;

  v_paid := (p_pay <> 'Udhaar');
  v_at   := coalesce(p_billed_at, now());

  insert into public.bills (shop_id, client_id, bill_no, billed_at, sub, disc_type, disc_val, disc,
                            gst_pct, gst, total, pay_method, customer, paid, paid_at, lines, source)
  values (s, p_client_id, v_no, v_at, (t->>'sub')::numeric, p_disc_type, (t->>'disc_val')::numeric,
          (t->>'disc')::numeric, (t->>'gst_pct')::numeric, (t->>'gst')::numeric,
          (t->>'total')::numeric, p_pay, coalesce(trim(p_customer), ''), v_paid,
          case when v_paid then v_at end, p_lines, p_source)
  returning * into r;

  if p_adjust_stock then
    update public.items i set stock = greatest(0, i.stock - q.qty)
    from (select l2->>'name' as name, sum((l2->>'qty')::numeric) as qty
          from jsonb_array_elements(p_lines) l2 group by 1) q
    where i.shop_id = s and i.name = q.name and i.stock is not null;
  end if;
  return r;
end $$;

create or replace function public.mark_bill_paid(p_bill_no int) returns public.bills
language plpgsql security invoker set search_path = public as $$
declare r public.bills;
begin
  update public.bills set paid = true, paid_at = now()
   where shop_id = public.my_shop_id() and bill_no = p_bill_no and not paid
  returning * into r;
  if not found then raise exception 'bill % not found or already paid', p_bill_no; end if;
  return r;
end $$;

create or replace function public.mark_customer_paid(p_customer text) returns int
language plpgsql security invoker set search_path = public as $$
declare n int;
begin
  update public.bills set paid = true, paid_at = now()
   where shop_id = public.my_shop_id() and pay_method = 'Udhaar' and not paid
     and lower(customer) = lower(trim(p_customer));
  get diagnostics n = row_count;
  if n = 0 then raise exception 'no unpaid udhaar for %', p_customer; end if;
  return n;
end $$;

-- Hard delete (mirrors the History tab's "Delete all saved bills" button).
-- For real accounting, change to a soft delete (deleted_at column).
create or replace function public.clear_bills() returns void
language sql security invoker set search_path = public as $$
  delete from public.bills where shop_id = public.my_shop_id();
$$;

do $$
declare f text;
begin
  foreach f in array array[
    'save_shop(text,text,text,int)', 'replace_items(jsonb)',
    'create_bill(jsonb,text,text,text,numeric,numeric,uuid,int,timestamptz,text,boolean)',
    'mark_bill_paid(int)', 'mark_customer_paid(text)', 'clear_bills()',
    'calc_totals(jsonb,text,numeric,numeric)']
  loop
    execute format('revoke all on function public.%s from public, anon', f);
    execute format('grant execute on function public.%s to authenticated', f);
  end loop;

  -- Table permissions for authenticated users (protected by RLS)
  grant all on table public.shops to authenticated;
  grant all on table public.items to authenticated;
  grant all on table public.bills to authenticated;
  grant all on table public.agent_runs to authenticated;
  grant all on table public.agent_actions to authenticated;
end $$;
