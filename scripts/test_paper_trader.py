#!/usr/bin/env python3
"""Regression tests for paper_trader resolve logic."""

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Patch DB_PATH before importing
import elo_model
tmpdb = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
elo_model.DB_PATH = Path(tmpdb.name)
tmpdb.close()

from paper_trader import resolve_trades, kelly_size
from elo_model import get_db


def setup_test_db():
    """Create test DB with known games and trades."""
    db = get_db()

    # Insert test games
    db.executemany("""
        INSERT OR REPLACE INTO games (id, league, date, season, home_team, away_team, home_score, away_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        ('test-1', 'nba', '2026-01-01', '2025-26', 'BOS', 'LAL', 110, 95),  # BOS (home) wins
        ('test-2', 'nba', '2026-01-01', '2025-26', 'CHI', 'OKC', 80, 100),  # OKC (away) wins
        ('test-3', 'nba', '2026-01-01', '2025-26', 'MIA', 'DET', 90, 105),  # DET (away) wins
        ('test-4', 'nba', '2026-01-01', '2025-26', 'DAL', 'CHA', 88, 75),   # DAL (home) wins
    ])

    # Insert test trades
    db.executemany("""
        INSERT OR REPLACE INTO paper_trades
        (id, date, league, market_slug, team, direction, entry_price,
         elo_probability, polymarket_price, edge_vs_poly, kelly_fraction,
         paper_amount, paper_shares)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        # Trade 1: Bet on BOS (home) via NO. BOS wins → should WIN
        ('test-t1', '2026-01-01', 'nba', 'aec-nba-lal-bos-2026-01-01',
         'BOS', 'NO', 0.75, 0.80, 0.75, 0.05, 0.05, 10.0, 13.33),

        # Trade 2: Bet on OKC (away) via YES. OKC wins → should WIN
        ('test-t2', '2026-01-01', 'nba', 'aec-nba-okc-chi-2026-01-01',
         'OKC', 'YES', 0.65, 0.72, 0.65, 0.07, 0.05, 10.0, 15.38),

        # Trade 3: Bet on MIA (home) via NO. DET (away) wins → should LOSE
        ('test-t3', '2026-01-01', 'nba', 'aec-nba-det-mia-2026-01-01',
         'MIA', 'NO', 0.60, 0.68, 0.60, 0.08, 0.05, 10.0, 16.67),

        # Trade 4: Bet on CHA (away) via YES. DAL (home) wins → should LOSE
        ('test-t4', '2026-01-01', 'nba', 'aec-nba-cha-dal-2026-01-01',
         'CHA', 'YES', 0.40, 0.55, 0.40, 0.15, 0.05, 10.0, 25.0),
    ])
    db.commit()
    return db


def test_resolve_logic():
    """Test that resolve correctly handles YES and NO direction trades."""
    db = setup_test_db()
    resolved = resolve_trades()

    # Check results
    trades = {t['id']: t for t in db.execute(
        "SELECT * FROM paper_trades WHERE id LIKE 'test-%'"
    ).fetchall()}

    failures = []

    # Trade 1: BOS home NO, BOS won → WIN
    if trades['test-t1']['outcome'] != 'WIN':
        failures.append(f"test-t1: BOS home NO, BOS won → expected WIN, got {trades['test-t1']['outcome']}")
    if trades['test-t1']['pnl'] <= 0:
        failures.append(f"test-t1: Expected positive PnL, got {trades['test-t1']['pnl']}")

    # Trade 2: OKC away YES, OKC won → WIN
    if trades['test-t2']['outcome'] != 'WIN':
        failures.append(f"test-t2: OKC away YES, OKC won → expected WIN, got {trades['test-t2']['outcome']}")
    if trades['test-t2']['pnl'] <= 0:
        failures.append(f"test-t2: Expected positive PnL, got {trades['test-t2']['pnl']}")

    # Trade 3: MIA home NO, MIA lost → LOSS
    if trades['test-t3']['outcome'] != 'LOSS':
        failures.append(f"test-t3: MIA home NO, MIA lost → expected LOSS, got {trades['test-t3']['outcome']}")
    if trades['test-t3']['pnl'] >= 0:
        failures.append(f"test-t3: Expected negative PnL, got {trades['test-t3']['pnl']}")

    # Trade 4: CHA away YES, CHA lost → LOSS
    if trades['test-t4']['outcome'] != 'LOSS':
        failures.append(f"test-t4: CHA away YES, CHA lost → expected LOSS, got {trades['test-t4']['outcome']}")
    if trades['test-t4']['pnl'] >= 0:
        failures.append(f"test-t4: Expected negative PnL, got {trades['test-t4']['pnl']}")

    if failures:
        print("❌ FAILURES:")
        for f in failures:
            print(f"  {f}")
        return False
    else:
        print(f"✅ All 4 resolve tests passed ({resolved} trades resolved)")
        return True


def test_kelly_sizing():
    """Test Kelly criterion position sizing."""
    failures = []

    # High prob, low price → should bet
    f, pos, shares = kelly_size(0.80, 0.65, 200.0)
    if pos <= 0:
        failures.append(f"80% prob at 65c should have positive size, got {pos}")

    # Low prob, high price → should not bet
    f, pos, shares = kelly_size(0.40, 0.60, 200.0)
    if pos > 0:
        failures.append(f"40% prob at 60c should have zero size, got {pos}")

    # Max position cap
    f, pos, shares = kelly_size(0.99, 0.50, 200.0)
    if pos > 200 * 0.05 + 0.01:  # 5% cap
        failures.append(f"Position {pos} exceeds 5% cap of $10")

    if failures:
        print("❌ Kelly FAILURES:")
        for f in failures:
            print(f"  {f}")
        return False
    else:
        print("✅ Kelly sizing tests passed")
        return True


if __name__ == '__main__':
    ok = True
    ok = test_resolve_logic() and ok
    ok = test_kelly_sizing() and ok

    # Clean up temp DB
    import os
    os.unlink(tmpdb.name)

    if not ok:
        sys.exit(1)
    print("\n✅ All tests passed!")
