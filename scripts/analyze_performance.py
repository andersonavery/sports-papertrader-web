#!/usr/bin/env python3
"""
Performance Analyzer for Paper Trading System

Usage:
  python3 analyze_performance.py              # Full performance report
  python3 analyze_performance.py calibration  # Calibration curve
  python3 analyze_performance.py by-sport     # Breakdown by sport
  python3 analyze_performance.py summary      # One-line summary
"""

import sys
import math
import sqlite3
from datetime import datetime
from pathlib import Path

# The paper_trades live in data/paper_trades.db, not the scripts/ Elo database.
_PROJECT_ROOT = Path(__file__).parent.parent
_DATA_DB_PATH = _PROJECT_ROOT / "data" / "paper_trades.db"

VIRTUAL_BANKROLL = 200.0

# Exclude pre-calibration trades that used fabricated $0.50 Polymarket prices.
CLEAN_TRADES_FILTER = "AND (data_quality IS NULL OR data_quality != 'fake_poly_price')"


def get_db():
    """Return a connection to the data database containing paper_trades."""
    db = sqlite3.connect(str(_DATA_DB_PATH))
    db.row_factory = sqlite3.Row
    return db


def full_report():
    """Generate comprehensive performance report."""
    db = get_db()

    # Overall stats (excluding fake-price trades)
    f = CLEAN_TRADES_FILTER
    total = db.execute(f"SELECT COUNT(*) as c FROM paper_trades WHERE 1=1 {f}").fetchone()['c']
    resolved = db.execute(f"SELECT COUNT(*) as c FROM paper_trades WHERE outcome IS NOT NULL {f}").fetchone()['c']
    wins = db.execute(f"SELECT COUNT(*) as c FROM paper_trades WHERE outcome = 'WIN' {f}").fetchone()['c']
    losses = db.execute(f"SELECT COUNT(*) as c FROM paper_trades WHERE outcome = 'LOSS' {f}").fetchone()['c']
    open_count = db.execute(f"SELECT COUNT(*) as c FROM paper_trades WHERE outcome IS NULL {f}").fetchone()['c']
    total_pnl = db.execute(f"SELECT COALESCE(SUM(pnl), 0) as s FROM paper_trades WHERE outcome IS NOT NULL {f}").fetchone()['s']
    total_invested = db.execute(f"SELECT COALESCE(SUM(paper_amount), 0) as s FROM paper_trades WHERE outcome IS NOT NULL {f}").fetchone()['s']

    print(f"\n{'═' * 70}")
    print(f"  PAPER TRADING PERFORMANCE REPORT")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═' * 70}")

    # ── Summary ──
    print(f"\n  📊 SUMMARY")
    print(f"  {'─' * 40}")
    print(f"  Starting Bankroll:  ${VIRTUAL_BANKROLL:.2f}")
    current = VIRTUAL_BANKROLL + total_pnl
    print(f"  Current Bankroll:   ${current:.2f}")
    print(f"  Total P&L:          {'$' if total_pnl >= 0 else '-$'}{abs(total_pnl):.2f} ({total_pnl/VIRTUAL_BANKROLL*100:+.1f}%)")
    print(f"  Total Trades:       {total}")
    print(f"  Resolved:           {resolved} ({wins}W - {losses}L)")
    print(f"  Open:               {open_count}")

    if resolved == 0:
        print(f"\n  ⚠️  No resolved trades yet. Come back after games complete.")
        print(f"      Run: python3 elo_model.py update && python3 paper_trader.py resolve")
        return

    win_rate = wins / resolved if resolved > 0 else 0
    roi = total_pnl / total_invested if total_invested > 0 else 0

    print(f"  Win Rate:           {win_rate*100:.1f}%")
    print(f"  ROI:                {roi*100:.1f}%")

    # ── Brier Score ──
    print(f"\n  📐 CALIBRATION")
    print(f"  {'─' * 40}")
    trades = db.execute(f"""
        SELECT elo_probability, outcome, direction FROM paper_trades
        WHERE outcome IS NOT NULL {CLEAN_TRADES_FILTER}
    """).fetchall()

    brier_sum = 0
    for t in trades:
        actual = 1.0 if t['outcome'] == 'WIN' else 0.0
        brier_sum += (t['elo_probability'] - actual) ** 2
    brier = brier_sum / len(trades)

    print(f"  Brier Score:        {brier:.4f}")
    print(f"    0.00 = perfect | 0.25 = random | < 0.20 = good")
    if brier < 0.15:
        print(f"    Rating: ⭐ EXCELLENT")
    elif brier < 0.20:
        print(f"    Rating: ✅ GOOD")
    elif brier < 0.25:
        print(f"    Rating: 🔶 MEDIOCRE — close to random")
    else:
        print(f"    Rating: ❌ POOR — worse than random")

    # ── Calibration Buckets ──
    print(f"\n  📊 CALIBRATION CURVE")
    print(f"  {'─' * 40}")
    print(f"  {'Predicted':>12} {'Actual':>8} {'Count':>7} {'Status'}")
    print(f"  {'─' * 12} {'─' * 8} {'─' * 7} {'─' * 10}")

    buckets = {}
    for t in trades:
        bucket = round(t['elo_probability'] * 10) / 10  # round to nearest 0.1
        if bucket not in buckets:
            buckets[bucket] = {'total': 0, 'wins': 0}
        buckets[bucket]['total'] += 1
        if t['outcome'] == 'WIN':
            buckets[bucket]['wins'] += 1

    for bucket in sorted(buckets.keys()):
        b = buckets[bucket]
        actual = b['wins'] / b['total'] if b['total'] > 0 else 0
        diff = actual - bucket
        status = "✅" if abs(diff) < 0.10 else "🔶" if abs(diff) < 0.20 else "❌"
        print(f"  {bucket*100:>10.0f}% {actual*100:>7.1f}% {b['total']:>7} {status} ({diff*100:+.1f}%)")

    # ── By Sport ──
    sport_breakdown(db, trades)

    # ── Risk Metrics ──
    print(f"\n  ⚠️  RISK METRICS")
    print(f"  {'─' * 40}")

    # Max drawdown
    pnl_series = db.execute(f"""
        SELECT pnl FROM paper_trades
        WHERE outcome IS NOT NULL {CLEAN_TRADES_FILTER} ORDER BY resolved_at
    """).fetchall()
    cumulative = 0
    peak = 0
    max_dd = 0
    for p in pnl_series:
        cumulative += p['pnl']
        peak = max(peak, cumulative)
        dd = peak - cumulative
        max_dd = max(max_dd, dd)

    print(f"  Max Drawdown:       ${max_dd:.2f} ({max_dd/VIRTUAL_BANKROLL*100:.1f}% of bankroll)")

    # Consecutive losses
    outcomes = [t['outcome'] for t in db.execute(
        f"SELECT outcome FROM paper_trades WHERE outcome IS NOT NULL {CLEAN_TRADES_FILTER} ORDER BY resolved_at"
    ).fetchall()]
    max_streak = 0
    current_streak = 0
    for o in outcomes:
        if o == 'LOSS':
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    print(f"  Max Loss Streak:    {max_streak}")

    # Average trade size
    avg_size = db.execute(f"""
        SELECT AVG(paper_amount) as a FROM paper_trades
        WHERE outcome IS NOT NULL {CLEAN_TRADES_FILTER}
    """).fetchone()['a']
    print(f"  Avg Trade Size:     ${avg_size:.2f}")

    # ── Sharpe Ratio ──
    if len(pnl_series) > 1:
        returns = [p['pnl'] / avg_size for p in pnl_series]
        avg_ret = sum(returns) / len(returns)
        variance = sum((r - avg_ret) ** 2 for r in returns) / (len(returns) - 1)
        std_ret = math.sqrt(variance) if variance > 0 else 0.001
        sharpe = avg_ret / std_ret if std_ret > 0 else 0
        # Annualize (assume ~5 trades per day, ~250 trading days)
        ann_sharpe = sharpe * math.sqrt(250 * 5) if len(pnl_series) > 10 else sharpe
        print(f"  Sharpe Ratio:       {sharpe:.3f} (per-trade)")

    # ── Recommendation ──
    print(f"\n  💡 RECOMMENDATION")
    print(f"  {'─' * 40}")

    if resolved < 20:
        print(f"  Too few trades ({resolved}) for reliable assessment.")
        print(f"  Need 50+ resolved for initial evaluation, 100+ for confidence.")
    elif brier > 0.25:
        print(f"  ❌ Model is performing WORSE than random. Pause trading.")
        print(f"  Review Elo parameters and edge threshold.")
    elif brier > 0.20:
        print(f"  🔶 Model is marginally useful. Consider:")
        print(f"  - Increasing edge threshold to 7%+")
        print(f"  - Reducing position sizes to eighth-Kelly")
    elif total_pnl > 0 and win_rate > 0.55:
        print(f"  ✅ Model shows promise! After 100+ trades, consider:")
        print(f"  - Transitioning to real trades with small positions")
        print(f"  - Maintaining strict Kelly discipline")
    else:
        print(f"  🔶 Mixed signals. Continue paper trading to {max(100, resolved*2)} trades.")


def sport_breakdown(db=None, trades=None):
    """Show performance breakdown by sport."""
    if db is None:
        db = get_db()

    print(f"\n  🏟️  BY SPORT")
    print(f"  {'─' * 40}")
    print(f"  {'Sport':<6} {'Trades':>7} {'W-L':>7} {'Win%':>6} {'P&L':>8} {'Brier':>7}")
    print(f"  {'─' * 6} {'─' * 7} {'─' * 7} {'─' * 6} {'─' * 8} {'─' * 7}")

    for league in ['nba', 'nhl']:
        stats = db.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
                COALESCE(SUM(pnl), 0) as pnl
            FROM paper_trades
            WHERE outcome IS NOT NULL {CLEAN_TRADES_FILTER} AND league = ?
        """, (league,)).fetchone()

        if stats['total'] == 0:
            continue

        win_pct = stats['wins'] / stats['total'] * 100
        record = f"{stats['wins']}-{stats['losses']}"

        # Brier for this sport
        sport_trades = db.execute(f"""
            SELECT elo_probability, outcome FROM paper_trades
            WHERE outcome IS NOT NULL {CLEAN_TRADES_FILTER} AND league = ?
        """, (league,)).fetchall()
        brier = sum((t['elo_probability'] - (1 if t['outcome'] == 'WIN' else 0)) ** 2
                     for t in sport_trades) / len(sport_trades) if sport_trades else 0

        pnl_str = f"${stats['pnl']:.2f}" if stats['pnl'] >= 0 else f"-${abs(stats['pnl']):.2f}"
        print(f"  {league.upper():<6} {stats['total']:>7} {record:>7} {win_pct:>5.1f}% {pnl_str:>8} {brier:>7.4f}")


def one_line_summary():
    """Print a single-line summary for agent use."""
    db = get_db()
    f = CLEAN_TRADES_FILTER
    resolved = db.execute(f"SELECT COUNT(*) as c FROM paper_trades WHERE outcome IS NOT NULL {f}").fetchone()['c']
    if resolved == 0:
        print("Paper trading: 0 resolved trades. No data yet.")
        return

    wins = db.execute(f"SELECT COUNT(*) as c FROM paper_trades WHERE outcome = 'WIN' {f}").fetchone()['c']
    pnl = db.execute(f"SELECT COALESCE(SUM(pnl), 0) as s FROM paper_trades WHERE outcome IS NOT NULL {f}").fetchone()['s']
    trades = db.execute(f"SELECT elo_probability, outcome FROM paper_trades WHERE outcome IS NOT NULL {f}").fetchall()
    brier = sum((t['elo_probability'] - (1 if t['outcome'] == 'WIN' else 0)) ** 2 for t in trades) / len(trades)

    print(f"Paper: {resolved} trades, {wins}W-{resolved-wins}L ({wins/resolved*100:.0f}%), "
          f"P&L: ${pnl:+.2f}, Brier: {brier:.3f}")


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0].lower() if args else 'full'

    if cmd in ('full', 'report'):
        full_report()
    elif cmd == 'calibration':
        full_report()  # calibration is part of full report
    elif cmd in ('by-sport', 'sport'):
        sport_breakdown()
    elif cmd == 'summary':
        one_line_summary()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
