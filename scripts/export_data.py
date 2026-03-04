#!/usr/bin/env python3
"""Export paper_trades.db data to a single JSON file for the static dashboard."""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

VIRTUAL_BANKROLL = 200.0

# Default DB location
DEFAULT_DB = Path("~/.copilot/skills/polymarket-api/paper_trades.db").expanduser()
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "data"


def get_conn(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def export(db_path):
    if not db_path.exists():
        print(f"DB not found: {db_path}")
        sys.exit(1)

    conn = get_conn(db_path)
    data = {}

    # --- Trades ---
    rows = conn.execute(
        "SELECT * FROM paper_trades ORDER BY date DESC, created_at DESC LIMIT 100"
    ).fetchall()
    data["trades"] = [dict(r) for r in rows]

    # --- Summary Stats ---
    total = conn.execute("SELECT COUNT(*) as c FROM paper_trades").fetchone()["c"]
    resolved = conn.execute(
        "SELECT COUNT(*) as c FROM paper_trades WHERE outcome IS NOT NULL"
    ).fetchone()["c"]
    wins = conn.execute(
        "SELECT COUNT(*) as c FROM paper_trades WHERE outcome = 'WIN'"
    ).fetchone()["c"]
    losses = conn.execute(
        "SELECT COUNT(*) as c FROM paper_trades WHERE outcome = 'LOSS'"
    ).fetchone()["c"]
    open_count = conn.execute(
        "SELECT COUNT(*) as c FROM paper_trades WHERE outcome IS NULL"
    ).fetchone()["c"]
    total_pnl = conn.execute(
        "SELECT COALESCE(SUM(pnl), 0) as s FROM paper_trades WHERE outcome IS NOT NULL"
    ).fetchone()["s"]
    total_invested = conn.execute(
        "SELECT COALESCE(SUM(paper_amount), 0) as s FROM paper_trades WHERE outcome IS NOT NULL"
    ).fetchone()["s"]
    open_invested = conn.execute(
        "SELECT COALESCE(SUM(paper_amount), 0) as s FROM paper_trades WHERE outcome IS NULL"
    ).fetchone()["s"]

    win_rate = (wins / resolved * 100) if resolved > 0 else 0
    roi = (total_pnl / total_invested * 100) if total_invested > 0 else 0
    current_bankroll = VIRTUAL_BANKROLL + total_pnl - open_invested

    data["stats"] = {
        "total": total,
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "open": open_count,
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 1),
        "roi": round(roi, 1),
        "bankroll": round(current_bankroll, 2),
        "starting_bankroll": VIRTUAL_BANKROLL,
    }

    # --- Elo Ratings ---
    for league in ["nba", "nhl", "cbb", "mls"]:
        rows = conn.execute(
            "SELECT * FROM elo_ratings WHERE league = ? ORDER BY rating DESC",
            (league,),
        ).fetchall()
        data[f"{league}_ratings"] = [dict(r) for r in rows]

    # --- P&L Series ---
    rows = conn.execute(
        "SELECT date, pnl FROM paper_trades WHERE outcome IS NOT NULL ORDER BY resolved_at"
    ).fetchall()
    cumulative = 0
    series = []
    for r in rows:
        cumulative += r["pnl"]
        series.append({"date": r["date"], "pnl": round(r["pnl"], 2), "cumulative": round(cumulative, 2)})
    data["pnl_series"] = series

    # --- Calibration ---
    rows = conn.execute(
        "SELECT elo_probability, outcome FROM paper_trades WHERE outcome IS NOT NULL"
    ).fetchall()
    buckets = {}
    brier_sum = 0
    for r in rows:
        actual = 1.0 if r["outcome"] == "WIN" else 0.0
        brier_sum += (r["elo_probability"] - actual) ** 2
        bucket = round(r["elo_probability"] * 10) / 10
        if bucket not in buckets:
            buckets[bucket] = {"total": 0, "wins": 0}
        buckets[bucket]["total"] += 1
        if r["outcome"] == "WIN":
            buckets[bucket]["wins"] += 1

    brier = round(brier_sum / len(rows), 4) if rows else 0
    cal = []
    for b in sorted(buckets):
        act = buckets[b]["wins"] / buckets[b]["total"]
        cal.append({"predicted": round(b * 100), "actual": round(act * 100, 1), "count": buckets[b]["total"]})
    data["calibration"] = cal
    data["brier"] = brier

    # --- Sport Breakdown ---
    breakdown = []
    for league in ["nba", "nhl", "cbb", "mls"]:
        stats = conn.execute(
            """SELECT COUNT(*) as total,
               SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
               COALESCE(SUM(pnl), 0) as pnl
            FROM paper_trades WHERE outcome IS NOT NULL AND league = ?""",
            (league,),
        ).fetchone()
        if stats["total"] > 0:
            trades = conn.execute(
                "SELECT elo_probability, outcome FROM paper_trades WHERE outcome IS NOT NULL AND league = ?",
                (league,),
            ).fetchall()
            b = sum((t["elo_probability"] - (1 if t["outcome"] == "WIN" else 0)) ** 2 for t in trades) / len(trades)
            breakdown.append({
                "league": league.upper(),
                "total": stats["total"],
                "wins": stats["wins"],
                "losses": stats["losses"],
                "win_rate": round(stats["wins"] / stats["total"] * 100, 1),
                "pnl": round(stats["pnl"], 2),
                "brier": round(b, 4),
            })
    data["sport_breakdown"] = breakdown

    # --- Risk Metrics ---
    pnl_rows = conn.execute(
        "SELECT pnl FROM paper_trades WHERE outcome IS NOT NULL ORDER BY resolved_at"
    ).fetchall()
    outcomes = conn.execute(
        "SELECT outcome FROM paper_trades WHERE outcome IS NOT NULL ORDER BY resolved_at"
    ).fetchall()
    avg_size = conn.execute(
        "SELECT AVG(paper_amount) as a FROM paper_trades WHERE outcome IS NOT NULL"
    ).fetchone()

    cumulative = 0
    peak = 0
    max_dd = 0
    for p in pnl_rows:
        cumulative += p["pnl"]
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)

    max_streak = 0
    streak = 0
    for o in outcomes:
        if o["outcome"] == "LOSS":
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    data["risk"] = {
        "max_drawdown": round(max_dd, 2),
        "max_loss_streak": max_streak,
        "avg_trade_size": round(avg_size["a"], 2) if avg_size["a"] else 0,
    }

    # --- Shadow Trades ---
    try:
        shadow_rows = conn.execute(
            "SELECT * FROM shadow_trades ORDER BY date DESC, created_at DESC LIMIT 50"
        ).fetchall()
        data["shadow_trades"] = [dict(r) for r in shadow_rows]

        shadow_resolved = conn.execute(
            "SELECT COUNT(*) as c FROM shadow_trades WHERE outcome IS NOT NULL"
        ).fetchone()["c"]
        shadow_wins = conn.execute(
            "SELECT COUNT(*) as c FROM shadow_trades WHERE outcome = 'WIN'"
        ).fetchone()["c"]
        shadow_losses = conn.execute(
            "SELECT COUNT(*) as c FROM shadow_trades WHERE outcome = 'LOSS'"
        ).fetchone()["c"]
        shadow_open = conn.execute(
            "SELECT COUNT(*) as c FROM shadow_trades WHERE outcome IS NULL"
        ).fetchone()["c"]
        shadow_pnl = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) as s FROM shadow_trades WHERE outcome IS NOT NULL"
        ).fetchone()["s"]

        data["shadow_stats"] = {
            "total": len(shadow_rows),
            "resolved": shadow_resolved,
            "wins": shadow_wins,
            "losses": shadow_losses,
            "open": shadow_open,
            "total_pnl": round(shadow_pnl, 2),
            "win_rate": round(shadow_wins / shadow_resolved * 100, 1) if shadow_resolved > 0 else 0,
        }
    except Exception:
        data["shadow_trades"] = []
        data["shadow_stats"] = {"total": 0, "resolved": 0, "wins": 0, "losses": 0, "open": 0, "total_pnl": 0, "win_rate": 0}

    data["last_updated"] = datetime.now(timezone.utc).isoformat()

    conn.close()

    # Write JSON
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUTPUT_DIR / "data.json"
    with open(out_file, "w") as f:
        json.dump(data, f, indent=2, default=str)

    print(f"Exported to {out_file} ({len(data['trades'])} trades, {len(data.get('nba_ratings', []))} NBA ratings)")


if __name__ == "__main__":
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    export(db)
