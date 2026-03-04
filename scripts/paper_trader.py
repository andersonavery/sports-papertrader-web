#!/usr/bin/env python3
"""
Paper Trading System for Polymarket — Automated Edge Detection & Simulation

Usage:
  python3 paper_trader.py scan              # Scan today's games for Elo signals
  python3 paper_trader.py scan --league nba # Scan NBA only
  python3 paper_trader.py trade --slug <slug> --team <team> --direction <YES|NO> \\
      --elo-prob <prob> --poly-price <price>  # Place trade with real BBO
  python3 paper_trader.py results            # Show recent paper trade results
  python3 paper_trader.py resolve            # Resolve completed games
  python3 paper_trader.py portfolio          # Show paper portfolio status
"""

import sys
import os
import json
import math
import sqlite3
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
import uuid

# Import from elo_model (same directory)
sys.path.insert(0, str(Path(__file__).parent))
from elo_model import (
    get_db, predict_game, predict_game_3way, ELO_CONFIG,
    get_todays_games_nba, get_todays_games_nhl,
    get_todays_games_cbb, get_todays_games_mls,
)

# ═══════════════════════════════════════════════════════════════
# PAPER TRADING CONFIGURATION
# ═══════════════════════════════════════════════════════════════

VIRTUAL_BANKROLL = 200.0  # $200 virtual bankroll
EDGE_THRESHOLD = 0.05     # 5% minimum edge to trade
FRICTION_BUFFER = 0.02    # 2% assumed transaction costs
KELLY_FRACTION = 0.25     # Quarter-Kelly
MAX_POSITION_PCT = 0.05   # 5% max single position
MAX_DAILY_TRADES = 5      # Cap daily trades to avoid overexposure
MIN_POSITION = 5.0        # $5 minimum position

# ESPN abbreviation → Polymarket slug abbreviation mapping
# (for constructing market slugs to check BBOs)
# ESPN abbreviation → Polymarket slug abbreviation mapping
# (for constructing market slugs to check BBOs)
# Keyed by "{league}:{espn_abbr}" when there are conflicts across sports
ESPN_TO_POLY = {
    # NBA
    "nba:GSW": "gs", "nba:NYK": "ny", "nba:PHX": "pho", "nba:SAS": "sa", "nba:NOP": "no",
    "nba:OKC": "okc", "nba:DEN": "den", "nba:CLE": "cle", "nba:BOS": "bos", "nba:DET": "det",
    "nba:HOU": "hou", "nba:SAC": "sac", "nba:UTA": "uta", "nba:MIL": "mil", "nba:CHI": "chi",
    "nba:BKN": "bkn", "nba:CHA": "cha", "nba:MIN": "min", "nba:LAL": "lal", "nba:LAC": "lac",
    "nba:TOR": "tor", "nba:PHI": "phi", "nba:IND": "ind", "nba:ATL": "atl", "nba:ORL": "orl",
    "nba:POR": "por", "nba:WAS": "was", "nba:MEM": "mem", "nba:MIA": "mia", "nba:DAL": "dal",
    # NHL
    "nhl:WPG": "wpg", "nhl:COL": "col", "nhl:EDM": "edm", "nhl:FLA": "fla", "nhl:DAL": "dal",
    "nhl:NYR": "nyr", "nhl:CAR": "car", "nhl:NJ": "nj", "nhl:TB": "tb", "nhl:BOS": "bos",
    "nhl:MIN": "min", "nhl:OTT": "ott", "nhl:VAN": "van", "nhl:CGY": "cgy", "nhl:PIT": "pit",
    "nhl:STL": "stl", "nhl:CBJ": "cbj", "nhl:NSH": "nas", "nhl:SEA": "sea", "nhl:LA": "la",
    "nhl:ANA": "ana", "nhl:DET": "det", "nhl:BUF": "buf", "nhl:CHI": "chi", "nhl:ARI": "ari",
    "nhl:MTL": "mon", "nhl:NYI": "nyi", "nhl:WSH": "was", "nhl:SJ": "sj", "nhl:VGK": "vgk",
    "nhl:TOR": "tor", "nhl:PHI": "phi", "nhl:UTA": "uta",
    # CBB (ESPN displayAbbreviation → Polymarket slug)
    "cbb:TEX": "tx", "cbb:ARK": "ark", "cbb:BAY": "bayl", "cbb:HOU": "hou",
    "cbb:UMD": "mary", "cbb:MSU": "mst", "cbb:OSU": "ohiost", "cbb:PSU": "pennst",
    "cbb:PUR": "pur", "cbb:RUTG": "rutger", "cbb:NW": "nw", "cbb:WIS": "wisc",
    "cbb:USC": "usc", "cbb:WASH": "wash", "cbb:ILL": "ill", "cbb:IU": "ind",
    "cbb:PITT": "pitt", "cbb:ND": "nd", "cbb:FSU": "flst", "cbb:STAN": "stan",
    "cbb:NOVA": "vill", "cbb:DEP": "depaul", "cbb:LUC": "loych", "cbb:SLU": "stlou",
    "cbb:UNM": "nmx", "cbb:UNT": "ntx", "cbb:CSU": "colst", "cbb:MEM": "mphs",
    "cbb:HAW": "hawaii", "cbb:UCR": "ucrvs", "cbb:UCI": "ucirv", "cbb:UCD": "ucdv",
    "cbb:UCSD": "ucsd", "cbb:CP": "calpol", "cbb:CSUF": "csufl", "cbb:LBSU": "lbst",
    "cbb:LMU": "loymry", "cbb:USD": "sd", "cbb:ORU": "oral", "cbb:UNF": "nfl",
    "cbb:RICE": "rice", "cbb:LR": "arlr", "cbb:WEBB": "gardwb", "cbb:UPST": "scup",
    "cbb:UE": "evans", "cbb:UNI": "niowa", "cbb:NMSU": "nmxst", "cbb:KC": "umkc",
    "cbb:UWG": "uwg", "cbb:BAMA": "bama", "cbb:AUB": "aub", "cbb:UK": "uk",
    "cbb:LSU": "lsu", "cbb:TENN": "tenn", "cbb:FLA": "fla", "cbb:UGA": "uga",
    "cbb:MIZ": "miz", "cbb:MISS": "miss", "cbb:SCAR": "scar", "cbb:TXAM": "txam",
    "cbb:VAN": "vandy", "cbb:OKLA": "okla",
    "cbb:IOWA": "iowa", "cbb:MICH": "mich", "cbb:MINN": "minn", "cbb:NEB": "neb",
    "cbb:ORE": "ore", "cbb:UCLA": "ucla",
    "cbb:DUKE": "duke", "cbb:UNC": "unc", "cbb:BC": "bc", "cbb:CLEM": "clem",
    "cbb:GT": "gt", "cbb:LOU": "lou", "cbb:SYR": "syr", "cbb:UVA": "uva",
    "cbb:VT": "vatech", "cbb:WAKE": "wake", "cbb:SMU": "smu", "cbb:CAL": "cal",
    "cbb:ARIZ": "ariz", "cbb:ASU": "asu", "cbb:BYU": "byu", "cbb:CIN": "cin",
    "cbb:COLO": "colo", "cbb:ISU": "iast", "cbb:KU": "kan", "cbb:KSU": "kanst",
    "cbb:OKST": "oklst", "cbb:TCU": "tcu", "cbb:TTU": "txtech", "cbb:UCF": "ucf",
    "cbb:UTAH": "utah", "cbb:WVU": "wvu",
    "cbb:BUT": "but", "cbb:UCONN": "uconn", "cbb:CREI": "crei", "cbb:GTOWN": "gtown",
    "cbb:MARQ": "marq", "cbb:PROV": "prov", "cbb:SH": "sh", "cbb:STJ": "stj",
    "cbb:XAV": "xav", "cbb:GONZ": "gonz", "cbb:DAY": "day", "cbb:SDSU": "sdsu",
    "cbb:PEPP": "pepp", "cbb:PORT": "port", "cbb:CSUN": "csunr", "cbb:CSUB": "csu",
    "cbb:UTEP": "utep", "cbb:USF": "sfl", "cbb:FAIR": "fair", "cbb:MAN": "manh",
    # MLS (ESPN abbreviation → Polymarket slug)
    "mls:ATL": "atl", "mls:ATX": "aus", "mls:MTL": "mim", "mls:CLT": "clt",
    "mls:CHI": "chi", "mls:COL": "col", "mls:CLB": "clb", "mls:DC": "dcu",
    "mls:CIN": "fcc", "mls:DAL": "dal", "mls:HOU": "hou", "mls:MIA": "mia",
    "mls:LA": "lag", "mls:LAFC": "laf", "mls:MIN": "min", "mls:NSH": "nas",
    "mls:NE": "ner", "mls:NYC": "nyc", "mls:RBNY": "nyr", "mls:ORL": "orl",
    "mls:PHI": "phi", "mls:POR": "por", "mls:RSL": "rsl", "mls:SD": "sdg",
    "mls:SJ": "sje", "mls:SEA": "sea", "mls:SKC": "skc", "mls:STL": "stl",
    "mls:TOR": "tor", "mls:VAN": "vwh",
}


def espn_to_poly_abbr(espn_abbr, league=None):
    """Convert ESPN team abbreviation to Polymarket slug abbreviation."""
    if league:
        # Try league-specific lookup first
        key = f"{league}:{espn_abbr}"
        if key in ESPN_TO_POLY:
            return ESPN_TO_POLY[key]
    # Fallback: try without league prefix (legacy NBA/NHL)
    return ESPN_TO_POLY.get(espn_abbr, espn_abbr.lower())


def build_market_slug(league, away_espn, home_espn, date_str=None):
    """Build a Polymarket market slug from ESPN abbreviations."""
    away = espn_to_poly_abbr(away_espn, league)
    home = espn_to_poly_abbr(home_espn, league)
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    prefix = "atc" if league == "mls" else "aec"
    return f"{prefix}-{league}-{away}-{home}-{date_str}"


# ═══════════════════════════════════════════════════════════════
# KELLY CRITERION
# ═══════════════════════════════════════════════════════════════

def kelly_size(prob, price, bankroll):
    """
    Calculate Kelly position size.
    prob: Your estimated win probability
    price: Market price (also the cost per share)
    bankroll: Available bankroll
    Returns: (kelly_fraction, position_size, num_shares)
    """
    if prob <= 0 or prob >= 1 or price <= 0 or price >= 1:
        return 0, 0, 0

    # Net odds: what you win per dollar risked
    b = (1.0 / price) - 1.0
    q = 1.0 - prob

    # Full Kelly
    f_star = (b * prob - q) / b

    if f_star <= 0:
        return 0, 0, 0

    # Fractional Kelly
    f = f_star * KELLY_FRACTION

    # Cap at max position
    f = min(f, MAX_POSITION_PCT)

    position = f * bankroll
    position = max(position, MIN_POSITION) if position > 0 else 0

    # Don't exceed bankroll
    position = min(position, bankroll * MAX_POSITION_PCT)

    shares = position / price if price > 0 else 0

    return f, position, shares


# ═══════════════════════════════════════════════════════════════
# PAPER TRADE EXECUTION
# ═══════════════════════════════════════════════════════════════

def get_current_bankroll(db):
    """Calculate current virtual bankroll from initial + resolved P&L."""
    result = db.execute("""
        SELECT COALESCE(SUM(pnl), 0) as total_pnl
        FROM paper_trades WHERE outcome IS NOT NULL
    """).fetchone()

    # Also subtract open positions' cost
    open_cost = db.execute("""
        SELECT COALESCE(SUM(paper_amount), 0) as open_cost
        FROM paper_trades WHERE outcome IS NULL
    """).fetchone()

    return VIRTUAL_BANKROLL + result['total_pnl'] - open_cost['open_cost']


def get_todays_trade_count(db):
    """Count how many paper trades placed today."""
    today = datetime.now().strftime("%Y-%m-%d")
    result = db.execute("""
        SELECT COUNT(*) as c FROM paper_trades WHERE date = ?
    """, (today,)).fetchone()
    return result['c']


def scan_and_trade(league=None):
    """
    Scan today's games, calculate edges, and place paper trades.
    """
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")

    # Check daily trade limit
    todays_trades = get_todays_trade_count(db)
    if todays_trades >= MAX_DAILY_TRADES:
        print(f"⚠️  Daily trade limit reached ({MAX_DAILY_TRADES}). Skipping scan.")
        return

    bankroll = get_current_bankroll(db)
    leagues = [league] if league else ['nba', 'nhl', 'cbb', 'mls']

    print(f"{'═' * 70}")
    print(f"  PAPER TRADING SCAN — {today}")
    print(f"  Virtual Bankroll: ${bankroll:.2f}")
    print(f"  Trades Today: {todays_trades}/{MAX_DAILY_TRADES}")
    print(f"{'═' * 70}")

    # Load Elo ratings
    ratings = {}
    for lg in leagues:
        rows = db.execute("SELECT team, rating FROM elo_ratings WHERE league = ?", (lg,)).fetchall()
        ratings[lg] = {r['team']: r['rating'] for r in rows}

    all_opportunities = []

    LEAGUE_ICONS = {'nba': '🏀', 'nhl': '🏒', 'cbb': '🎓', 'mls': '⚽'}

    for lg in leagues:
        if lg == 'nba':
            games = get_todays_games_nba()
        elif lg == 'nhl':
            games = get_todays_games_nhl()
        elif lg == 'cbb':
            games = get_todays_games_cbb()
        elif lg == 'mls':
            games = get_todays_games_mls()
        else:
            continue

        if not games:
            print(f"\n  No {lg.upper()} games found for today.")
            continue

        icon = LEAGUE_ICONS.get(lg, '🏟️')
        print(f"\n  {icon} {lg.upper()} Games:")

        if lg == 'mls':
            # 3-way market: home/draw/away
            print(f"  {'Matchup':<25} {'Home%':>7} {'Draw%':>7} {'Away%':>7} {'Signal'}")
            print(f"  {'─' * 25} {'─' * 7} {'─' * 7} {'─' * 7} {'─' * 10}")
        else:
            print(f"  {'Matchup':<25} {'Elo Away':>9} {'Elo Home':>9} {'Edge':>7} {'Signal'}")
            print(f"  {'─' * 25} {'─' * 9} {'─' * 9} {'─' * 7} {'─' * 10}")

        for game in games:
            if game['status'] not in ('Scheduled', 'Pre-Game'):
                continue

            if lg == 'mls':
                # 3-way prediction for soccer
                home_prob, draw_prob, away_prob = predict_game_3way(
                    lg, game['away_team'], game['home_team'], ratings.get(lg, {}))

                # MLS slug format: atc-mls-{home}-{away}-{date}
                base_slug = build_market_slug(lg, game['away_team'], game['home_team'], today)

                # Check each outcome for edge
                for team, prob, direction, suffix in [
                    (game['home_team'], home_prob, 'YES', f"-{espn_to_poly_abbr(game['home_team'], lg)}"),
                    (game['away_team'], away_prob, 'YES', f"-{espn_to_poly_abbr(game['away_team'], lg)}"),
                ]:
                    deviation = abs(prob - 0.33)  # vs 3-way fair value
                    signal = "STRONG" if deviation > 0.20 else "MODERATE" if deviation > 0.10 else "WEAK"
                    if prob > 0.40 and deviation > 0.07:
                        all_opportunities.append({
                            'league': lg,
                            'game': game,
                            'team': team,
                            'direction': direction,
                            'elo_prob': prob,
                            'deviation': deviation,
                            'signal': signal,
                            'slug': base_slug + suffix,
                        })

                matchup = f"{game['away_team']} @ {game['home_team']}"
                max_prob = max(home_prob, away_prob)
                signal = "⭐ STRONG" if max_prob > 0.53 else "🔶 MOD" if max_prob > 0.43 else "⚪ WEAK"
                print(f"  {matchup:<25} {home_prob*100:>6.1f}% {draw_prob*100:>6.1f}% "
                      f"{away_prob*100:>6.1f}% {signal}")
            else:
                # 2-way prediction for basketball/hockey
                home_prob, away_prob = predict_game(lg, game['away_team'], game['home_team'], ratings.get(lg, {}))

                slug = build_market_slug(lg, game['away_team'], game['home_team'], today)

                for team, prob, direction in [
                    (game['away_team'], away_prob, 'YES'),
                    (game['home_team'], home_prob, 'NO'),
                ]:
                    deviation = abs(prob - 0.5)
                    signal = "STRONG" if deviation > 0.25 else "MODERATE" if deviation > 0.15 else "WEAK"

                    if prob > 0.5 and deviation > 0.10:
                        all_opportunities.append({
                            'league': lg,
                            'game': game,
                            'team': team,
                            'direction': direction,
                            'elo_prob': prob,
                            'deviation': deviation,
                            'signal': signal,
                            'slug': slug,
                        })

                matchup = f"{game['away_team']} @ {game['home_team']}"
                elo_away = ratings.get(lg, {}).get(game['away_team'], 1500)
                elo_home = ratings.get(lg, {}).get(game['home_team'], 1500)
                max_dev = max(away_prob, home_prob) - 0.5
                signal = "⭐ STRONG" if max_dev > 0.25 else "🔶 MOD" if max_dev > 0.15 else "⚪ WEAK"
                print(f"  {matchup:<25} {elo_away:>9.1f} {elo_home:>9.1f} {max_dev*100:>6.1f}% {signal}")

    # Print strong signals — agent must provide real BBO prices to place trades
    strong_opps = [o for o in all_opportunities if o['signal'] == 'STRONG']

    if strong_opps:
        print(f"\n{'═' * 70}")
        print(f"  STRONG SIGNALS (need real Polymarket BBO to trade)")
        print(f"{'═' * 70}")
        print(f"  {'Team':<6} {'Dir':<4} {'Elo%':>6} {'Slug'}")
        print(f"  {'─'*6} {'─'*4} {'─'*6} {'─'*40}")

        for opp in sorted(strong_opps, key=lambda x: -x['deviation']):
            print(f"  {opp['team']:<6} {opp['direction']:<4} "
                  f"{opp['elo_prob']*100:>5.1f}% {opp['slug']}")

        print(f"\n  ⚠️  To place trades, use: paper_trader.py trade --slug <slug> "
              f"--poly-price <bbo_price>")
    else:
        print(f"\n  ⚪ No strong signals found.")

    return strong_opps


def place_paper_trade(slug, team, direction, elo_prob, poly_price, league=None):
    """
    Place a single paper trade with real Polymarket BBO price.
    Called by the agent after fetching actual market data.

    Args:
        slug: Polymarket market slug
        team: Team abbreviation we're betting on
        direction: 'YES' or 'NO' (market side)
        elo_prob: Our Elo-based win probability for the team
        poly_price: Real Polymarket price (from BBO mid-price)
        league: Sport league (inferred from slug if omitted)
    """
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")

    if league is None:
        parts = slug.split('-')
        league = parts[1] if len(parts) > 1 else 'nba'

    # Calculate edge against real market price
    edge_raw = elo_prob - poly_price
    edge_net = abs(edge_raw) - FRICTION_BUFFER

    if edge_net < EDGE_THRESHOLD:
        print(f"  ⚪ No edge: Elo={elo_prob:.1%} vs Poly={poly_price:.1%} "
              f"(net edge {edge_net:.1%} < {EDGE_THRESHOLD:.0%} threshold)")
        return None

    # Check daily limits
    todays_trades = get_todays_trade_count(db)
    if todays_trades >= MAX_DAILY_TRADES:
        print(f"  ⚠️  Daily trade limit reached ({MAX_DAILY_TRADES}).")
        return None

    bankroll = get_current_bankroll(db)

    # Entry price = real Polymarket price (what we'd actually pay)
    entry_price = poly_price
    f, position, shares = kelly_size(elo_prob, entry_price, bankroll)

    if position < MIN_POSITION:
        print(f"  ⚪ Position too small: ${position:.2f} < ${MIN_POSITION:.2f}")
        return None

    trade_id = (f"pt-{league}-{team}-"
                f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
                f"{uuid.uuid4().hex[:4]}")

    db.execute("""
        INSERT INTO paper_trades
        (id, date, league, market_slug, team, direction, entry_price,
         elo_probability, polymarket_price, edge_vs_poly, kelly_fraction,
         paper_amount, paper_shares)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trade_id, today, league, slug, team,
        direction, entry_price, elo_prob,
        poly_price, edge_raw,
        f, position, shares,
    ))
    db.commit()

    print(f"  ✅ {direction} {team} ({league.upper()}) "
          f"@ ${entry_price:.2f} (Poly: ${poly_price:.2f}) | "
          f"Elo: {elo_prob*100:.1f}% | Edge: {edge_net*100:.1f}% | "
          f"Size: ${position:.2f} ({f*100:.1f}% bankroll)")
    return trade_id


def resolve_trades():
    """Check completed games and resolve paper trades."""
    db = get_db()

    # Get unresolved trades
    open_trades = db.execute("""
        SELECT * FROM paper_trades WHERE outcome IS NULL ORDER BY date
    """).fetchall()

    if not open_trades:
        print("No unresolved paper trades.")
        return 0

    resolved = 0
    for trade in open_trades:
        league = trade['league']
        team = trade['team']
        trade_date = trade['date']

        # Check if the game has been played
        game = db.execute("""
            SELECT * FROM games
            WHERE league = ? AND date = ? AND (home_team = ? OR away_team = ?)
            ORDER BY date DESC LIMIT 1
        """, (league, trade_date, team, team)).fetchone()

        if not game:
            # Try fetching latest results
            continue

        # Determine if the team won
        if team == game['home_team']:
            won = game['home_score'] > game['away_score']
        else:
            won = game['away_score'] > game['home_score']

        # We always bet ON our team winning (YES=away wins, NO=home wins).
        # `won` tracks whether our team won, so trade_won = won always.
        trade_won = won

        # Calculate P&L
        entry_price = trade['entry_price']
        paper_shares = trade['paper_shares']

        if trade_won:
            pnl = paper_shares * (1.0 - entry_price)  # shares pay $1, cost was entry_price
            outcome = 'WIN'
        else:
            pnl = -trade['paper_amount']  # lose entire investment
            outcome = 'LOSS'

        db.execute("""
            UPDATE paper_trades
            SET outcome = ?, pnl = ?, resolved_at = datetime('now')
            WHERE id = ?
        """, (outcome, pnl, trade['id']))

        print(f"  {'✅' if trade_won else '❌'} {trade['team']} ({trade['league'].upper()}) "
              f"{trade['direction']} @ ${entry_price:.2f} → {outcome} "
              f"(P&L: {'$' if pnl >= 0 else '-$'}{abs(pnl):.2f})")
        resolved += 1

    db.commit()
    return resolved


def place_shadow_trade(slug, team, direction, elo_prob, poly_price,
                       reason_skipped, sportsbook_prob=None, league=None):
    """
    Place a shadow trade — a trade the model said NO to, tracked for learning.
    Uses a fixed $10 notional amount (not from bankroll).
    """
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")

    if league is None:
        parts = slug.split('-')
        league = parts[1] if len(parts) > 1 else 'nba'

    shadow_amount = 10.0
    entry_price = poly_price
    shares = shadow_amount / entry_price if entry_price > 0 else 0
    edge = elo_prob - poly_price

    trade_id = (f"sh-{league}-{team}-"
                f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
                f"{uuid.uuid4().hex[:4]}")

    db.execute("""
        INSERT INTO shadow_trades
        (id, date, league, market_slug, team, direction, entry_price,
         elo_probability, sportsbook_probability, polymarket_price,
         edge_vs_poly, reason_skipped, shadow_amount, shadow_shares)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trade_id, today, league, slug, team, direction, entry_price,
        elo_prob, sportsbook_prob, poly_price, edge, reason_skipped,
        shadow_amount, shares,
    ))
    db.commit()

    print(f"  👻 SHADOW {direction} {team} ({league.upper()}) "
          f"@ ${entry_price:.2f} | Elo: {elo_prob*100:.1f}% | "
          f"Edge: {edge*100:+.1f}% | Reason: {reason_skipped}")
    return trade_id


def resolve_shadow_trades():
    """Resolve shadow trades using same game results."""
    db = get_db()

    open_shadows = db.execute("""
        SELECT * FROM shadow_trades WHERE outcome IS NULL ORDER BY date
    """).fetchall()

    if not open_shadows:
        print("No unresolved shadow trades.")
        return 0

    resolved = 0
    for trade in open_shadows:
        game = db.execute("""
            SELECT * FROM games
            WHERE league = ? AND date = ? AND (home_team = ? OR away_team = ?)
            ORDER BY date DESC LIMIT 1
        """, (trade['league'], trade['date'], trade['team'], trade['team'])).fetchone()

        if not game:
            continue

        if trade['team'] == game['home_team']:
            won = game['home_score'] > game['away_score']
        else:
            won = game['away_score'] > game['home_score']

        trade_won = won
        entry_price = trade['entry_price']
        shares = trade['shadow_shares']

        if trade_won:
            pnl = shares * (1.0 - entry_price)
            outcome = 'WIN'
        else:
            pnl = -trade['shadow_amount']
            outcome = 'LOSS'

        db.execute("""
            UPDATE shadow_trades
            SET outcome = ?, pnl = ?, resolved_at = datetime('now')
            WHERE id = ?
        """, (outcome, pnl, trade['id']))

        icon = '👻✅' if trade_won else '👻❌'
        print(f"  {icon} SHADOW {trade['team']} ({trade['league'].upper()}) "
              f"{trade['direction']} @ ${entry_price:.2f} → {outcome} "
              f"(P&L: {'$' if pnl >= 0 else '-$'}{abs(pnl):.2f}) "
              f"[skipped: {trade['reason_skipped']}]")
        resolved += 1

    db.commit()
    return resolved
    """Show recent paper trade results."""
    db = get_db()

    trades = db.execute("""
        SELECT * FROM paper_trades ORDER BY date DESC, created_at DESC LIMIT 20
    """).fetchall()

    if not trades:
        print("No paper trades found. Run 'scan' to place paper trades.")
        return

    bankroll = get_current_bankroll(db)
    total_pnl = db.execute("SELECT COALESCE(SUM(pnl), 0) as s FROM paper_trades WHERE outcome IS NOT NULL").fetchone()['s']
    total_resolved = db.execute("SELECT COUNT(*) as c FROM paper_trades WHERE outcome IS NOT NULL").fetchone()['c']
    wins = db.execute("SELECT COUNT(*) as c FROM paper_trades WHERE outcome = 'WIN'").fetchone()['c']
    losses = db.execute("SELECT COUNT(*) as c FROM paper_trades WHERE outcome = 'LOSS'").fetchone()['c']
    open_trades = db.execute("SELECT COUNT(*) as c FROM paper_trades WHERE outcome IS NULL").fetchone()['c']

    print(f"\n{'═' * 70}")
    print(f"  PAPER TRADING RESULTS")
    print(f"{'═' * 70}")
    print(f"  Virtual Bankroll:  ${bankroll:.2f} (started: ${VIRTUAL_BANKROLL:.2f})")
    print(f"  Total P&L:         {'$' if total_pnl >= 0 else '-$'}{abs(total_pnl):.2f}")
    print(f"  Resolved Trades:   {total_resolved} ({wins}W - {losses}L)")
    if total_resolved > 0:
        print(f"  Win Rate:          {wins/total_resolved*100:.1f}%")
    print(f"  Open Trades:       {open_trades}")

    # Brier score
    if total_resolved > 0:
        brier_data = db.execute("""
            SELECT elo_probability, outcome FROM paper_trades WHERE outcome IS NOT NULL
        """).fetchall()
        brier_sum = 0
        for t in brier_data:
            actual = 1.0 if t['outcome'] == 'WIN' else 0.0
            brier_sum += (t['elo_probability'] - actual) ** 2
        brier = brier_sum / len(brier_data)
        print(f"  Brier Score:       {brier:.4f} (lower is better, 0.25 = random)")

    print(f"\n  {'Date':<12} {'League':<5} {'Team':<6} {'Dir':<4} {'Price':>6} {'Elo%':>6} {'Size':>7} {'Result':<6} {'P&L':>8}")
    print(f"  {'─'*12} {'─'*5} {'─'*6} {'─'*4} {'─'*6} {'─'*6} {'─'*7} {'─'*6} {'─'*8}")

    for t in trades:
        outcome = t['outcome'] or 'OPEN'
        pnl_str = f"${t['pnl']:.2f}" if t['pnl'] is not None else '—'
        icon = '✅' if outcome == 'WIN' else '❌' if outcome == 'LOSS' else '⏳'
        print(f"  {t['date']:<12} {t['league']:<5} {t['team']:<6} {t['direction']:<4} "
              f"${t['entry_price']:.2f} {t['elo_probability']*100:>5.1f}% "
              f"${t['paper_amount']:.2f} {icon}{outcome:<5} {pnl_str:>8}")


def show_portfolio():
    """Show current paper portfolio status."""
    db = get_db()
    bankroll = get_current_bankroll(db)

    open_trades = db.execute("""
        SELECT * FROM paper_trades WHERE outcome IS NULL ORDER BY date
    """).fetchall()

    total_invested = sum(t['paper_amount'] for t in open_trades)

    print(f"\n{'═' * 60}")
    print(f"  PAPER PORTFOLIO")
    print(f"{'═' * 60}")
    print(f"  Available Cash:    ${bankroll:.2f}")
    print(f"  Open Positions:    {len(open_trades)} (${total_invested:.2f} invested)")
    print(f"  Total Portfolio:   ${bankroll + total_invested:.2f}")

    if open_trades:
        print(f"\n  {'Date':<12} {'Team':<6} {'Dir':<4} {'Entry':>6} {'Elo%':>6} {'Size':>7}")
        print(f"  {'─'*12} {'─'*6} {'─'*4} {'─'*6} {'─'*6} {'─'*7}")
        for t in open_trades:
            print(f"  {t['date']:<12} {t['team']:<6} {t['direction']:<4} "
                  f"${t['entry_price']:.2f} {t['elo_probability']*100:>5.1f}% ${t['paper_amount']:.2f}")


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0].lower()

    if cmd == 'scan':
        league = None
        if '--league' in args:
            idx = args.index('--league')
            if idx + 1 < len(args):
                league = args[idx + 1].lower()
        scan_and_trade(league)

    elif cmd == 'trade':
        # Parse trade arguments
        def get_arg(name):
            if name in args:
                idx = args.index(name)
                if idx + 1 < len(args):
                    return args[idx + 1]
            return None

        slug = get_arg('--slug')
        team = get_arg('--team')
        direction = get_arg('--direction')
        elo_prob = get_arg('--elo-prob')
        poly_price = get_arg('--poly-price')
        league = get_arg('--league')

        if not all([slug, team, direction, elo_prob, poly_price]):
            print("  ❌ Missing required arguments.")
            print("  Usage: paper_trader.py trade --slug <slug> --team <team> "
                  "--direction <YES|NO> --elo-prob <prob> --poly-price <price>")
            sys.exit(1)

        place_paper_trade(
            slug=slug, team=team.upper(), direction=direction.upper(),
            elo_prob=float(elo_prob), poly_price=float(poly_price),
            league=league,
        )

    elif cmd == 'resolve':
        resolved = resolve_trades()
        shadow_resolved = resolve_shadow_trades()
        print(f"\n  Resolved {resolved} paper trades + {shadow_resolved} shadow trades.")

    elif cmd == 'results':
        show_results()

    elif cmd == 'portfolio':
        show_portfolio()

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
