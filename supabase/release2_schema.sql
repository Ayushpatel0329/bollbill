-- =====================================================================
-- Release 2 Updates: Purchase Import & Udhaar Agent
-- Safe to re-run: tables use if not exists
-- =====================================================================

-- 1. Extend items with purchase price & HSN code
alter table if exists public.items 
  add column if not exists purchase_price numeric(12,2) default 0 check (purchase_price >= 0),
  add column if not exists hsn_code text default '',
  add column if not exists gst_rate numeric(5,2) default 0 check (gst_rate >= 0);

-- 2. Item Aliases table
create table if not exists public.item_aliases (
  id uuid primary key default gen_random_uuid(),
  shop_id uuid not null references public.shops(id) on delete cascade,
  item_id uuid not null references public.items(id) on delete cascade,
  alias text not null,
  normalized_alias text not null,
  source text not null default 'manual' check (source in ('manual', 'import', 'ai')),
  created_at timestamptz not null default now(),
  unique(shop_id, normalized_alias)
);

-- 3. Import batches & history for undo
create table if not exists public.import_batches (
  id uuid primary key default gen_random_uuid(),
  shop_id uuid not null references public.shops(id) on delete cascade,
  filename text not null,
  status text not null default 'committed' check (status in ('pending', 'committed', 'undone')),
  summary jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.import_batch_rows (
  id uuid primary key default gen_random_uuid(),
  batch_id uuid not null references public.import_batches(id) on delete cascade,
  item_id uuid not null references public.items(id) on delete cascade,
  before_data jsonb,
  after_data jsonb,
  created_at timestamptz not null default now()
);

-- 4. Udhaar Agent Settings
create table if not exists public.agent_settings (
  shop_id uuid primary key references public.shops(id) on delete cascade,
  enabled boolean not null default true,
  remind_after_days int not null default 7 check (remind_after_days between 1 and 60),
  followup_gap_days int not null default 7 check (followup_gap_days between 1 and 30),
  max_reminders int not null default 3 check (max_reminders between 1 and 5),
  language text not null default 'hinglish' check (language in ('hindi', 'english', 'hinglish')),
  reply_mode text not null default 'manual' check (reply_mode in ('manual', 'auto_safe')),
  quiet_hours_start int not null default 20, -- 8 PM
  quiet_hours_end int not null default 9,   -- 9 AM
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 5. Udhaar Reminders (Inbox queue)
create table if not exists public.udhaar_reminders (
  id uuid primary key default gen_random_uuid(),
  shop_id uuid not null references public.shops(id) on delete cascade,
  udhaar_id uuid not null references public.bills(id) on delete cascade,
  customer_name text not null,
  customer_phone text not null default '',
  amount_due numeric(12,2) not null check (amount_due > 0),
  level int not null default 1 check (level between 1 and 3),
  draft_text text not null,
  final_text text,
  status text not null default 'pending' check (status in ('pending', 'approved', 'denied', 'sent', 'failed', 'cancelled')),
  escalation_reason text,
  snooze_until timestamptz,
  approved_at timestamptz,
  sent_at timestamptz,
  created_at timestamptz not null default now(),
  unique(udhaar_id, level)
);

-- 6. Customer Flags (opt out & promised pay date)
create table if not exists public.customer_flags (
  id uuid primary key default gen_random_uuid(),
  shop_id uuid not null references public.shops(id) on delete cascade,
  customer_phone text not null,
  do_not_remind boolean not null default false,
  promise_date timestamptz,
  notes text,
  updated_at timestamptz not null default now(),
  unique(shop_id, customer_phone)
);

-- 7. Audit log for all automated actions
create table if not exists public.agent_audit_log (
  id uuid primary key default gen_random_uuid(),
  shop_id uuid not null references public.shops(id) on delete cascade,
  action text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- Row Level Security for new tables
alter table public.item_aliases enable row level security;
alter table public.import_batches enable row level security;
alter table public.import_batch_rows enable row level security;
alter table public.agent_settings enable row level security;
alter table public.udhaar_reminders enable row level security;
alter table public.customer_flags enable row level security;
alter table public.agent_audit_log enable row level security;

-- Policies
create policy "item_aliases_owner" on public.item_aliases for all using (shop_id = public.my_shop_id());
create policy "import_batches_owner" on public.import_batches for all using (shop_id = public.my_shop_id());
create policy "import_batch_rows_owner" on public.import_batch_rows for all using (batch_id in (select id from public.import_batches where shop_id = public.my_shop_id()));
create policy "agent_settings_owner" on public.agent_settings for all using (shop_id = public.my_shop_id());
create policy "udhaar_reminders_owner" on public.udhaar_reminders for all using (shop_id = public.my_shop_id());
create policy "customer_flags_owner" on public.customer_flags for all using (shop_id = public.my_shop_id());
create policy "agent_audit_log_owner" on public.agent_audit_log for all using (shop_id = public.my_shop_id());
