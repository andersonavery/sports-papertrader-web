# Sports Paper Trader — Web Dashboard

A lightweight web dashboard for monitoring and controlling a sports prediction paper trading system powered by Elo ratings.

## What It Does

- **View paper trades** with P&L tracking and cumulative charts
- **Monitor Elo ratings** for NBA and NHL teams
- **See today's predictions** with signal strength indicators
- **Track performance** — Brier score, calibration curves, win rate, Sharpe ratio
- **Control actions** — Scan for trades, resolve outcomes, update Elo ratings from the UI

## Stack

- **Backend**: FastAPI + Jinja2
- **Frontend**: HTMX + Tailwind CSS (CDN) + Chart.js
- **Database**: SQLite (shared with the CLI paper trading system)
- **Local only** — no auth, no deployment, just `uvicorn`

## Setup

```bash
# 1. Clone and install
git clone https://github.com/YOUR_USERNAME/sports-papertrader-web.git
cd sports-papertrader-web
pip install -e .

# 2. Configure path to your paper trading scripts/DB
cp .env.example .env
# Edit .env to point POLY_SKILLS_DIR at your skills directory

# 3. Run
uvicorn app.main:app --reload
# Open http://localhost:8000
```

## Prerequisites

The paper trading system must be set up first:
- `elo_model.py` — Elo rating engine
- `paper_trader.py` — Paper trade scanner
- `analyze_performance.py` — Performance analytics
- `paper_trades.db` — SQLite database

These live at `~/.copilot/skills/polymarket-api/` by default.

## Architecture

```
Browser ──HTMX──▶ FastAPI ──▶ SQLite (paper_trades.db)
                     │
                     ├──▶ elo_model.py (subprocess)
                     ├──▶ paper_trader.py
                     └──▶ analyze_performance.py
```
