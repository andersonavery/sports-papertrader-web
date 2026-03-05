# Copilot Instructions — Sports PaperTrader

## Project overview
Sports PaperTrader is a lightweight web dashboard for monitoring and controlling a sports prediction paper trading system. It combines custom Elo ratings (NBA, NHL, CBB, MLS) with Polymarket prediction market prices to detect edges and simulate trades with a virtual bankroll ($200). The system uses a triangulation gate — requiring Elo model agreement, Polymarket edge, and sportsbook line confirmation — before placing any trade.

Two interfaces exist:
1. **Web dashboard** (this repo) — FastAPI + HTMX for real-time monitoring and control
2. **Static GitHub Pages dashboard** — auto-deployed daily via GitHub Actions with exported JSON data

## Directory structure
```
sports-papertrader-web/
├── app/
│   ├── main.py          # FastAPI app entry point, mounts routers + static files
│   ├── db.py            # SQLite data access layer (trades, ratings, stats, calibration)
│   ├── services.py      # Subprocess calls to CLI scripts with file locking
│   ├── settings.py      # Config via python-dotenv (POLY_SKILLS_DIR, DB_PATH)
│   ├── routes/
│   │   ├── pages.py     # Full-page HTML routes (dashboard, partials)
│   │   ├── actions.py   # HTMX POST endpoints (scan, resolve, update-elo)
│   │   └── api.py       # JSON API endpoints (/api/pnl, /api/calibration, etc.)
│   ├── templates/
│   │   ├── layout.html      # Base template (Tailwind CDN, HTMX, Chart.js)
│   │   ├── dashboard.html   # Main dashboard page
│   │   └── partials/        # HTMX partial templates (trades, performance, etc.)
│   └── static/
│       ├── app.js       # Client-side JavaScript
│       └── styles.css   # Custom styles
├── data/
│   └── paper_trades.db  # SQLite database (copy for CI/local dev)
├── scripts/             # CLI tools (also used as subprocesses by the web app)
│   ├── elo_model.py     # Elo rating engine (build, update, predict, today)
│   ├── paper_trader.py  # Paper trade scanner (scan, resolve, trade, portfolio)
│   ├── analyze_performance.py  # Performance analytics (calibration, by-sport, summary)
│   ├── export_data.py   # Export DB → JSON for static GitHub Pages dashboard
│   ├── polymarket_slugs.py     # Polymarket slug construction helpers
│   └── test_paper_trader.py    # Tests for paper trading logic
├── docs/                # Static GitHub Pages dashboard
│   ├── index.html       # Self-contained static dashboard
│   └── data/            # Exported JSON data (auto-generated)
├── .github/workflows/
│   └── deploy.yml       # Daily auto-update: Elo → resolve → export → deploy Pages
├── pyproject.toml       # Python project config (FastAPI, uvicorn, jinja2, python-dotenv)
└── .env.example         # Environment config template
```

## Tech stack
- **Backend**: FastAPI + Jinja2 (Python ≥ 3.11)
- **Frontend**: HTMX 2.0 + Tailwind CSS (CDN) + Chart.js 4.x
- **Database**: SQLite (`paper_trades.db`) — shared with the CLI paper trading system
- **Server**: Uvicorn with `--reload` for development
- **Dependencies**: fastapi ≥ 0.115, uvicorn[standard] ≥ 0.34, jinja2 ≥ 3.1, python-dotenv ≥ 1.0
- **CI/CD**: GitHub Actions (daily cron) → GitHub Pages static deployment

## Commands
```bash
# Install
pip install -e .

# Run development server
uvicorn app.main:app --reload
# → http://localhost:8000

# CLI tools (run from project root or scripts/ directory)
python scripts/elo_model.py update          # Update Elo ratings from latest game results
python scripts/elo_model.py ratings nba     # Show current NBA Elo ratings
python scripts/elo_model.py today nba       # Today's NBA predictions
python scripts/paper_trader.py scan         # Scan for tradeable edges
python scripts/paper_trader.py resolve      # Resolve completed trades
python scripts/paper_trader.py portfolio    # Show portfolio status
python scripts/analyze_performance.py       # Full performance report
python scripts/export_data.py              # Export DB to JSON for static dashboard
```

## Architecture
```
Browser ──HTMX──▶ FastAPI ──▶ SQLite (paper_trades.db)
                     │
                     ├──▶ elo_model.py (subprocess)    ← Elo rating updates + predictions
                     ├──▶ paper_trader.py (subprocess)  ← Trade scanning + resolution
                     └──▶ analyze_performance.py        ← Performance analytics

GitHub Actions (daily cron at 10 AM UTC):
  elo_model.py update → paper_trader.py resolve → export_data.py → GitHub Pages deploy
```

### Key data flow
1. **Elo model** fetches game results from ESPN/nba_api, updates team ratings in SQLite
2. **Paper trader** scans today's games, compares Elo probabilities vs. Polymarket prices, applies triangulation gate, places shadow/paper trades
3. **Web dashboard** reads SQLite directly for display, invokes scripts via subprocess for actions
4. **Export script** dumps all data to JSON for the static GitHub Pages dashboard

## Key patterns

### HTMX-driven UI (no SPA)
- Full page loads for the dashboard via Jinja2 templates
- HTMX `hx-post` for actions (scan, resolve, update-elo) → returns HTML partials
- After any action, JavaScript triggers HTMX refresh of trades and performance panels
- No client-side framework, no build step — just server-rendered HTML with HTMX interactivity

### Shadow trading with triangulation gate
- **Shadow trades**: Logged when the Elo model detects an edge but the triangulation gate blocks execution
- **Paper trades**: Only placed when ALL three signals agree (Elo edge, Polymarket price, sportsbook line)
- The gate prevents overtrading on single-signal noise

### Position sizing
- Quarter-Kelly criterion (`KELLY_FRACTION = 0.25`)
- 5% max single position (`MAX_POSITION_PCT = 0.05`)
- 5% minimum edge threshold (`EDGE_THRESHOLD = 0.05`)
- 2% friction buffer for transaction costs
- $5 minimum / 5 max daily trades

### Dark theme
- `class="dark"` on `<html>`. Custom Tailwind config with `surface` and `accent` color tokens.
- Background: `#0f172a`, cards: `#1e293b`. Text: `text-slate-200`.
- Never use `bg-white`, `text-black`, or light mode colors.

### Database tables
- `paper_trades` — all paper trades with outcome, P&L, Elo probability, Polymarket price
- `shadow_trades` — edge-detected but gate-blocked trades
- `elo_ratings` — current team ratings per league
- `model_versions` — Elo model version history
- `trade_retrospectives` — what-if analysis for each model version

## Dependencies
The paper trading engine lives at `~/.copilot/skills/polymarket-api/` by default (configurable via `POLY_SKILLS_DIR` in `.env`). The `scripts/` directory contains copies of the key scripts for CI/CD use. The web app invokes the skills directory versions via subprocess.

## Conventions
- Commit messages: conventional commits (`fix:`, `feat:`, `chore:`)
- Always include `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer
- PRs for all code changes; direct commits OK for config/meta files
- Python 3.11+ features are fine (match statements, tomllib, etc.)
- SQLite queries in `db.py` — keep raw SQL, no ORM
- Jinja2 templates use `{% include "partials/..." %}` for reusable components

## When I say "create a work item"
Create a GitHub issue in `andersonavery/sports-papertrader-web` with:
1. **Clear title** — prefix with `fix:`, `feat:`, or `chore:`
2. **Summary** — one paragraph describing the problem or feature
3. **Root cause / motivation** — what's broken or why this matters
4. **Files to investigate** — list specific file paths
5. **Fix needed** — checklist of concrete tasks
6. **Acceptance criteria** — how to verify it's done
7. Apply labels: `bug`, `enhancement`, or `chore`
