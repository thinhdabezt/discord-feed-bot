# Discord Feed Bot — Debian / Termux starter

Python async Discord feed monitor. The first milestone supports RSS/Atom and PostgreSQL.
X, Instagram and Facebook collectors are intentionally added in later phases through
official APIs or permitted public-data access. This project does not bypass login,
CAPTCHA, access controls, or platform rate limits.

## Runtime layout

- Android Termux runs Debian through `proot-distro`.
- Python bot and feed collectors run inside Debian.
- PostgreSQL runs on another host.
- RSS collectors use HTTP and parse RSS/Atom; no Docker or RSSBridge is required.

## Debian setup

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip build-essential libpq-dev
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
cp sources.example.yaml sources.yaml
```

Edit `.env` and `sources.yaml`. Keep `.env` private; never commit tokens/passwords.

For Termux + proot-distro, run the Debian commands inside the Debian shell. Do not use
`sudo` if the Debian image is already running as root.

## Configure PostgreSQL

Create a database and a dedicated user on the PostgreSQL host. Ensure PostgreSQL listens
on the LAN interface, firewall allows only the bot host/network, and `pg_hba.conf` grants
the dedicated user access. Prefer a VPN or TLS when connecting over untrusted networks.

Set `DATABASE_URL` in `.env`, for example:

```text
postgresql+asyncpg://bot_user:password@192.168.1.20:5432/discord_feed_bot
```

## Run

```bash
source .venv/bin/activate
bash scripts/check-env.sh
bash scripts/start.sh
```

The bot exposes `/health` and `/poll` slash commands. The first run syncs commands and
creates tables if `DB_CREATE_TABLES=true`. This is for development only; add Alembic
migrations before production.

## Enable an RSS source

Edit `sources.yaml`:

```yaml
sources:
  - key: example-news
    name: Example News
    platform: rss
    url: https://example.com/feed.xml
    enabled: true
```

Polling defaults to 600 seconds. New items are deduplicated by `(source_id, external_id)`.

## Current scope / next milestones

1. Foundation: configuration, Discord lifecycle, PostgreSQL, RSS, 10-minute polling.
2. Reliability: Alembic, per-source state/checkpoints, retry/backoff, health metrics.
3. X: official API adapter, subject to API access and rate limits.
4. Instagram and Facebook: supported Graph API adapters for eligible accounts/pages.
5. Optional public HTML extraction only where permitted and stable; do not evade access controls.

## Termux process notes

- Use `termux-wake-lock` in Termux to reduce sleep-related interruptions.
- Run the bot inside `tmux` so the session can detach.
- Disable battery optimization for Termux if Android offers that setting.
- Android may still terminate background processes; this is not equivalent to a VPS.
