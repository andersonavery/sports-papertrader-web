import sqlite3
from app.settings import DB_PATH

VIRTUAL_BANKROLL = 200.0


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_trades(limit=50):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM paper_trades ORDER BY date DESC, created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_open_trades():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM paper_trades WHERE outcome IS NULL ORDER BY date"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_elo_ratings(league):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM elo_ratings WHERE league = ? ORDER BY rating DESC",
        (league,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_summary_stats():
    conn = get_conn()
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
    conn.close()

    win_rate = (wins / resolved * 100) if resolved > 0 else 0
    roi = (total_pnl / total_invested * 100) if total_invested > 0 else 0
    current_bankroll = VIRTUAL_BANKROLL + total_pnl - open_invested

    return {
        "total": total,
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "open": open_count,
        "total_pnl": total_pnl,
        "win_rate": win_rate,
        "roi": roi,
        "bankroll": current_bankroll,
        "starting_bankroll": VIRTUAL_BANKROLL,
    }


def get_pnl_series():
    conn = get_conn()
    rows = conn.execute(
        "SELECT date, pnl FROM paper_trades WHERE outcome IS NOT NULL ORDER BY resolved_at"
    ).fetchall()
    conn.close()

    cumulative = 0
    series = []
    for r in rows:
        cumulative += r["pnl"]
        series.append({"date": r["date"], "pnl": r["pnl"], "cumulative": round(cumulative, 2)})
    return series


def get_calibration_data():
    conn = get_conn()
    rows = conn.execute(
        "SELECT elo_probability, outcome FROM paper_trades WHERE outcome IS NOT NULL"
    ).fetchall()
    conn.close()

    if not rows:
        return [], 0

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

    brier = brier_sum / len(rows)
    cal = []
    for b in sorted(buckets):
        actual = buckets[b]["wins"] / buckets[b]["total"]
        cal.append({
            "predicted": round(b * 100),
            "actual": round(actual * 100, 1),
            "count": buckets[b]["total"],
        })
    return cal, round(brier, 4)


def get_sport_breakdown():
    conn = get_conn()
    breakdown = []
    for league in ["nba", "nhl", "cbb", "mls"]:
        stats = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
                COALESCE(SUM(pnl), 0) as pnl
            FROM paper_trades WHERE outcome IS NOT NULL AND league = ?
        """, (league,)).fetchone()
        if stats["total"] > 0:
            # Brier per sport
            trades = conn.execute(
                "SELECT elo_probability, outcome FROM paper_trades WHERE outcome IS NOT NULL AND league = ?",
                (league,),
            ).fetchall()
            brier = sum(
                (t["elo_probability"] - (1 if t["outcome"] == "WIN" else 0)) ** 2
                for t in trades
            ) / len(trades)
            breakdown.append({
                "league": league.upper(),
                "total": stats["total"],
                "wins": stats["wins"],
                "losses": stats["losses"],
                "win_rate": round(stats["wins"] / stats["total"] * 100, 1),
                "pnl": round(stats["pnl"], 2),
                "brier": round(brier, 4),
            })
    conn.close()
    return breakdown


def get_risk_metrics():
    conn = get_conn()
    pnl_rows = conn.execute(
        "SELECT pnl FROM paper_trades WHERE outcome IS NOT NULL ORDER BY resolved_at"
    ).fetchall()
    outcomes = conn.execute(
        "SELECT outcome FROM paper_trades WHERE outcome IS NOT NULL ORDER BY resolved_at"
    ).fetchall()
    avg_size = conn.execute(
        "SELECT AVG(paper_amount) as a FROM paper_trades WHERE outcome IS NOT NULL"
    ).fetchone()
    conn.close()

    # Max drawdown
    cumulative = 0
    peak = 0
    max_dd = 0
    for p in pnl_rows:
        cumulative += p["pnl"]
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)

    # Max loss streak
    max_streak = 0
    streak = 0
    for o in outcomes:
        if o["outcome"] == "LOSS":
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    return {
        "max_drawdown": round(max_dd, 2),
        "max_loss_streak": max_streak,
        "avg_trade_size": round(avg_size["a"], 2) if avg_size["a"] else 0,
    }
