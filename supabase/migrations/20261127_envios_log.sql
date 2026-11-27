-- Histórico de envios pro Drive (lido no painel de ADM).
-- Só o backend acessa, com a service key. RLS ligado e sem policy = ninguém mais lê.
create table if not exists public.envios_log (
  envio_id      text primary key,
  user_id       uuid references auth.users(id) on delete set null,
  user_email    text,
  autor         text not null,
  processo      text not null,
  caminho       text,
  url           text,
  total_itens   integer not null default 0,
  enviados      integer not null default 0,
  ja_existiam   integer not null default 0,
  falhas        integer not null default 0,
  criado_em     timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create index if not exists envios_log_criado_em_idx on public.envios_log (criado_em desc);

alter table public.envios_log enable row level security;
