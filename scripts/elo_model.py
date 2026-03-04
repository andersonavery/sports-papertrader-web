#!/usr/bin/env python3
"""
Elo Rating Engine for NBA + NHL + CBB + MLS — Polymarket Edge Detection

Usage:
  python3 elo_model.py build              # Build/rebuild ratings from historical data
  python3 elo_model.py ratings nba        # Show current NBA Elo ratings
  python3 elo_model.py ratings nhl        # Show current NHL Elo ratings
  python3 elo_model.py ratings cbb        # Show current CBB Elo ratings
  python3 elo_model.py ratings mls        # Show current MLS Elo ratings
  python3 elo_model.py predict nba OKC DET  # Predict OKC (away) @ DET (home)
  python3 elo_model.py today nba          # Show predictions for today's games
"""

import sys
import os
import json
import math
import sqlite3
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

DB_PATH = Path(__file__).parent / "paper_trades.db"
DATA_DIR = Path(__file__).parent / "data"

# Elo parameters (tuned per sport)
ELO_CONFIG = {
    "nba": {
        "k_factor": 20,
        "home_advantage": 100,
        "initial_rating": 1500,
        "season_regression": 1/3,  # regress 1/3 toward mean at season start
        "mov_multiplier": True,    # margin-of-victory adjustment
    },
    "nhl": {
        "k_factor": 8,
        "home_advantage": 35,
        "initial_rating": 1500,
        "season_regression": 1/3,
        "mov_multiplier": True,
    },
    "cbb": {
        "k_factor": 15,
        "home_advantage": 80,
        "initial_rating": 1500,
        "season_regression": 1/2,  # higher regression — less data per team
        "mov_multiplier": True,
    },
    "mls": {
        "k_factor": 25,
        "home_advantage": 100,
        "initial_rating": 1500,
        "season_regression": 1/4,  # moderate — shorter offseason
        "mov_multiplier": False,   # soccer goals too rare for MOV
    },
}

# NBA team abbreviation normalization (NBA.com → standard)
NBA_ABBREV_MAP = {
    "PHX": "PHO", "GS": "GSW", "SA": "SAS", "NY": "NYK", "NO": "NOP",
    # Most are already standard
}

# ═══════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════

def get_db():
    """Get SQLite connection with tables created."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS games (
            id TEXT PRIMARY KEY,
            league TEXT NOT NULL,
            date TEXT NOT NULL,
            season TEXT,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            home_score INTEGER,
            away_score INTEGER,
            overtime INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_games_league_date ON games(league, date);

        CREATE TABLE IF NOT EXISTS elo_ratings (
            team TEXT NOT NULL,
            league TEXT NOT NULL,
            rating REAL NOT NULL,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (team, league)
        );

        CREATE TABLE IF NOT EXISTS paper_trades (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            league TEXT,
            market_slug TEXT,
            team TEXT,
            direction TEXT,
            entry_price REAL,
            elo_probability REAL,
            sportsbook_probability REAL,
            polymarket_price REAL,
            edge_vs_poly REAL,
            edge_vs_sportsbook REAL,
            kelly_fraction REAL,
            paper_amount REAL,
            paper_shares REAL,
            outcome TEXT,
            closing_price REAL,
            pnl REAL,
            resolved_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS performance_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            total_trades INTEGER,
            wins INTEGER,
            losses INTEGER,
            total_pnl REAL,
            brier_score REAL,
            beat_close_rate REAL,
            bankroll REAL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS build_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league TEXT,
            games_loaded INTEGER,
            seasons TEXT,
            built_at TEXT DEFAULT (datetime('now'))
        );
    """)
    db.commit()
    return db


# ═══════════════════════════════════════════════════════════════
# DATA INGESTION
# ═══════════════════════════════════════════════════════════════

def fetch_nba_games(seasons=None):
    """Fetch NBA game results via nba_api."""
    from nba_api.stats.endpoints import leaguegamefinder
    import time

    if seasons is None:
        seasons = ["2024-25", "2025-26"]

    all_games = []
    for season in seasons:
        print(f"  Fetching NBA {season}...")
        time.sleep(1)  # rate limit
        gf = leaguegamefinder.LeagueGameFinder(
            season_nullable=season,
            league_id_nullable='00',
            season_type_nullable='Regular Season'
        )
        df = gf.get_data_frames()[0]

        # Each game appears twice (once per team). Deduplicate by GAME_ID.
        seen = set()
        for _, row in df.iterrows():
            gid = row['GAME_ID']
            if gid in seen:
                continue
            seen.add(gid)

            matchup = row['MATCHUP']
            team_abbr = row['TEAM_ABBREVIATION']

            if ' vs. ' in matchup:
                # This team is home
                home = team_abbr
                away = matchup.split(' vs. ')[1].strip()
            elif ' @ ' in matchup:
                # This team is away
                away = team_abbr
                home = matchup.split(' @ ')[1].strip()
            else:
                continue

            # Find the other team's row for scores
            other_rows = df[(df['GAME_ID'] == gid) & (df['TEAM_ABBREVIATION'] != team_abbr)]

            if ' vs. ' in matchup:
                home_pts = int(row['PTS'])
                away_pts = int(other_rows.iloc[0]['PTS']) if len(other_rows) > 0 else 0
            else:
                away_pts = int(row['PTS'])
                home_pts = int(other_rows.iloc[0]['PTS']) if len(other_rows) > 0 else 0

            all_games.append({
                'id': f"nba-{gid}",
                'league': 'nba',
                'date': row['GAME_DATE'],
                'season': season,
                'home_team': home,
                'away_team': away,
                'home_score': home_pts,
                'away_score': away_pts,
                'overtime': 0,
            })

    return all_games


def fetch_nhl_games(seasons=None):
    """Fetch NHL game results via ESPN API."""
    if seasons is None:
        # NHL 2024-25 season: Oct 2024 - Jun 2025
        # NHL 2025-26 season: Oct 2025 - Jun 2026
        seasons = [
            ("2024-25", "20241001", "20250630"),
            ("2025-26", "20251001", "20260630"),
        ]

    all_games = []
    for season_name, start_date, end_date in seasons:
        print(f"  Fetching NHL {season_name}...")
        # ESPN API paginates by date range — fetch month by month
        current = datetime.strptime(start_date, "%Y%m%d")
        end = min(datetime.strptime(end_date, "%Y%m%d"), datetime.now())

        while current <= end:
            date_str = current.strftime("%Y%m%d")
            url = f"https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates={date_str}&limit=50"
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                resp = urllib.request.urlopen(req, timeout=10)
                data = json.loads(resp.read())
            except Exception:
                current += timedelta(days=1)
                continue

            for event in data.get('events', []):
                comp = event['competitions'][0]
                status = comp['status']['type']['description']
                if status != 'Final':
                    continue

                teams = comp['competitors']
                home = [t for t in teams if t['homeAway'] == 'home'][0]
                away = [t for t in teams if t['homeAway'] == 'away'][0]

                game_id = event['id']
                ot = 1 if any('OT' in str(comp.get('status', {}).get('type', {}).get('detail', ''))
                          or 'SO' in str(comp.get('status', {}).get('type', {}).get('detail', ''))
                          for _ in [1]) else 0

                all_games.append({
                    'id': f"nhl-{game_id}",
                    'league': 'nhl',
                    'date': current.strftime("%Y-%m-%d"),
                    'season': season_name,
                    'home_team': home['team']['abbreviation'],
                    'away_team': away['team']['abbreviation'],
                    'home_score': int(home['score']),
                    'away_score': int(away['score']),
                    'overtime': ot,
                })

            current += timedelta(days=1)

    return all_games


def fetch_cbb_games(seasons=None):
    """Fetch college basketball game results via ESPN API."""
    if seasons is None:
        seasons = [
            ("2024-25", "20241101", "20250410"),
            ("2025-26", "20251101", "20260410"),
        ]

    all_games = []
    for season_name, start_date, end_date in seasons:
        print(f"  Fetching CBB {season_name}...")
        current = datetime.strptime(start_date, "%Y%m%d")
        end = min(datetime.strptime(end_date, "%Y%m%d"), datetime.now())

        while current <= end:
            date_str = current.strftime("%Y%m%d")
            url = (f"https://site.api.espn.com/apis/site/v2/sports/basketball/"
                   f"mens-college-basketball/scoreboard?dates={date_str}&limit=200&groups=50")
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                resp = urllib.request.urlopen(req, timeout=10)
                data = json.loads(resp.read())
            except Exception:
                current += timedelta(days=1)
                continue

            for event in data.get('events', []):
                comp = event['competitions'][0]
                status = comp['status']['type']['description']
                if status != 'Final':
                    continue

                teams = comp['competitors']
                home = [t for t in teams if t['homeAway'] == 'home'][0]
                away = [t for t in teams if t['homeAway'] == 'away'][0]
                game_id = event['id']

                all_games.append({
                    'id': f"cbb-{game_id}",
                    'league': 'cbb',
                    'date': current.strftime("%Y-%m-%d"),
                    'season': season_name,
                    'home_team': home['team']['abbreviation'],
                    'away_team': away['team']['abbreviation'],
                    'home_score': int(home['score']),
                    'away_score': int(away['score']),
                    'overtime': 0,
                })

            current += timedelta(days=1)

    return all_games


def fetch_mls_games(seasons=None):
    """Fetch MLS game results via ESPN API."""
    if seasons is None:
        seasons = [
            ("2025", "20250201", "20251115"),
            ("2026", "20260201", "20261115"),
        ]

    all_games = []
    for season_name, start_date, end_date in seasons:
        print(f"  Fetching MLS {season_name}...")
        current = datetime.strptime(start_date, "%Y%m%d")
        end = min(datetime.strptime(end_date, "%Y%m%d"), datetime.now())

        while current <= end:
            date_str = current.strftime("%Y%m%d")
            url = (f"https://site.api.espn.com/apis/site/v2/sports/soccer/"
                   f"usa.1/scoreboard?dates={date_str}&limit=50")
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                resp = urllib.request.urlopen(req, timeout=10)
                data = json.loads(resp.read())
            except Exception:
                current += timedelta(days=1)
                continue

            for event in data.get('events', []):
                comp = event['competitions'][0]
                status = comp['status']['type']['description']
                if status != 'Full Time' and status != 'Final':
                    continue

                teams = comp['competitors']
                home = [t for t in teams if t['homeAway'] == 'home'][0]
                away = [t for t in teams if t['homeAway'] == 'away'][0]
                game_id = event['id']

                all_games.append({
                    'id': f"mls-{game_id}",
                    'league': 'mls',
                    'date': current.strftime("%Y-%m-%d"),
                    'season': season_name,
                    'home_team': home['team']['abbreviation'],
                    'away_team': away['team']['abbreviation'],
                    'home_score': int(home['score']),
                    'away_score': int(away['score']),
                    'overtime': 0,
                })

            current += timedelta(days=1)

    return all_games


def load_games_to_db(games, db=None):
    """Insert games into SQLite, skipping duplicates."""
    if db is None:
        db = get_db()
    inserted = 0
    for g in games:
        try:
            db.execute("""
                INSERT OR IGNORE INTO games
                (id, league, date, season, home_team, away_team, home_score, away_score, overtime)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (g['id'], g['league'], g['date'], g['season'],
                  g['home_team'], g['away_team'], g['home_score'], g['away_score'], g['overtime']))
            inserted += 1
        except sqlite3.IntegrityError:
            pass
    db.commit()
    return inserted


# ═══════════════════════════════════════════════════════════════
# ELO ENGINE
# ═══════════════════════════════════════════════════════════════

def expected_score(rating_a, rating_b):
    """Calculate expected score for team A against team B."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def mov_multiplier(margin, elo_diff):
    """Margin-of-victory multiplier (FiveThirtyEight style)."""
    # Log-based, adjusted for autocorrelation with Elo diff
    return math.log(max(abs(margin), 1) + 1) * (2.2 / ((elo_diff * 0.001) + 2.2))


def calculate_elo_ratings(league):
    """
    Calculate Elo ratings from all historical games for a league.
    Returns dict of {team: rating}.
    """
    db = get_db()
    config = ELO_CONFIG[league]

    games = db.execute("""
        SELECT * FROM games WHERE league = ? ORDER BY date, id
    """, (league,)).fetchall()

    if not games:
        print(f"  No games found for {league}. Run 'build' first.")
        return {}

    ratings = {}
    games_played = {}
    wins = {}
    losses = {}
    current_season = None

    for game in games:
        home = game['home_team']
        away = game['away_team']
        season = game['season']

        # Season regression
        if season != current_season and current_season is not None:
            for team in ratings:
                ratings[team] = config['initial_rating'] + (1 - config['season_regression']) * (ratings[team] - config['initial_rating'])
            current_season = season
        elif current_season is None:
            current_season = season

        # Initialize new teams
        for team in [home, away]:
            if team not in ratings:
                ratings[team] = config['initial_rating']
                games_played[team] = 0
                wins[team] = 0
                losses[team] = 0

        # Add home advantage
        home_rating = ratings[home] + config['home_advantage']
        away_rating = ratings[away]

        # Expected scores
        exp_home = expected_score(home_rating, away_rating)

        # Actual result
        home_score = game['home_score']
        away_score = game['away_score']

        if home_score > away_score:
            actual_home = 1.0
            wins[home] += 1
            losses[away] += 1
        else:
            actual_home = 0.0
            wins[away] += 1
            losses[home] += 1

        games_played[home] += 1
        games_played[away] += 1

        # K-factor with optional MOV multiplier
        k = config['k_factor']
        if config['mov_multiplier']:
            margin = abs(home_score - away_score)
            elo_diff = abs(home_rating - away_rating)
            k *= mov_multiplier(margin, elo_diff)

        # Update ratings (home advantage is NOT added to stored rating)
        ratings[home] += k * (actual_home - exp_home)
        ratings[away] += k * ((1 - actual_home) - (1 - exp_home))

    # Save to DB
    for team in ratings:
        db.execute("""
            INSERT OR REPLACE INTO elo_ratings (team, league, rating, games_played, wins, losses, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (team, league, round(ratings[team], 1), games_played.get(team, 0),
              wins.get(team, 0), losses.get(team, 0)))
    db.commit()

    return ratings


def predict_game(league, away_team, home_team, ratings=None):
    """
    Predict win probability for a game.
    Returns (home_win_prob, away_win_prob).
    """
    if ratings is None:
        db = get_db()
        rows = db.execute("""
            SELECT team, rating FROM elo_ratings WHERE league = ?
        """, (league,)).fetchall()
        ratings = {r['team']: r['rating'] for r in rows}

    config = ELO_CONFIG[league]

    home_rating = ratings.get(home_team, config['initial_rating']) + config['home_advantage']
    away_rating = ratings.get(away_team, config['initial_rating'])

    home_prob = expected_score(home_rating, away_rating)
    away_prob = 1.0 - home_prob

    return home_prob, away_prob


def predict_game_3way(league, away_team, home_team, ratings=None):
    """
    Predict 3-way outcome for soccer (home win / draw / away win).
    Uses Elo expected score + empirical draw rate adjustment.
    Returns (home_win_prob, draw_prob, away_win_prob).
    """
    if ratings is None:
        db = get_db()
        rows = db.execute("""
            SELECT team, rating FROM elo_ratings WHERE league = ?
        """, (league,)).fetchall()
        ratings = {r['team']: r['rating'] for r in rows}

    config = ELO_CONFIG[league]

    home_rating = ratings.get(home_team, config['initial_rating']) + config['home_advantage']
    away_rating = ratings.get(away_team, config['initial_rating'])

    # Base Elo expected scores
    home_exp = expected_score(home_rating, away_rating)
    away_exp = 1.0 - home_exp

    # Draw probability: higher when teams are close in strength
    # Empirical MLS draw rate is ~23%. Adjust based on Elo closeness.
    base_draw_rate = 0.23
    elo_diff = abs(home_rating - away_rating)
    # Draw more likely when teams are close, less when big gap
    draw_adj = max(0.10, base_draw_rate * (1.0 - elo_diff / 800.0))
    draw_adj = min(draw_adj, 0.40)

    # Redistribute: subtract draw probability proportionally from both sides
    home_prob = home_exp * (1.0 - draw_adj)
    away_prob = away_exp * (1.0 - draw_adj)
    draw_prob = draw_adj

    return home_prob, draw_prob, away_prob


def get_todays_games_nba():
    """Fetch today's NBA schedule from ESPN."""
    today = datetime.now().strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={today}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
    except Exception as e:
        print(f"Error fetching NBA schedule: {e}")
        return []

    games = []
    for event in data.get('events', []):
        comp = event['competitions'][0]
        teams = comp['competitors']
        home = [t for t in teams if t['homeAway'] == 'home'][0]
        away = [t for t in teams if t['homeAway'] == 'away'][0]
        status = comp['status']['type']['description']

        games.append({
            'home_team': home['team']['abbreviation'],
            'away_team': away['team']['abbreviation'],
            'home_name': home['team']['displayName'],
            'away_name': away['team']['displayName'],
            'status': status,
            'game_time': event.get('date', ''),
        })
    return games


def get_todays_games_nhl():
    """Fetch today's NHL schedule from ESPN."""
    today = datetime.now().strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates={today}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
    except Exception as e:
        print(f"Error fetching NHL schedule: {e}")
        return []

    games = []
    for event in data.get('events', []):
        comp = event['competitions'][0]
        teams = comp['competitors']
        home = [t for t in teams if t['homeAway'] == 'home'][0]
        away = [t for t in teams if t['homeAway'] == 'away'][0]
        status = comp['status']['type']['description']

        games.append({
            'home_team': home['team']['abbreviation'],
            'away_team': away['team']['abbreviation'],
            'home_name': home['team']['displayName'],
            'away_name': away['team']['displayName'],
            'status': status,
            'game_time': event.get('date', ''),
        })
    return games


def get_todays_games_cbb():
    """Fetch today's college basketball schedule from ESPN."""
    today = datetime.now().strftime("%Y%m%d")
    url = (f"https://site.api.espn.com/apis/site/v2/sports/basketball/"
           f"mens-college-basketball/scoreboard?dates={today}&limit=200&groups=50")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
    except Exception as e:
        print(f"Error fetching CBB schedule: {e}")
        return []

    games = []
    for event in data.get('events', []):
        comp = event['competitions'][0]
        teams = comp['competitors']
        home = [t for t in teams if t['homeAway'] == 'home'][0]
        away = [t for t in teams if t['homeAway'] == 'away'][0]
        status = comp['status']['type']['description']

        games.append({
            'home_team': home['team']['abbreviation'],
            'away_team': away['team']['abbreviation'],
            'home_name': home['team']['displayName'],
            'away_name': away['team']['displayName'],
            'status': status,
            'game_time': event.get('date', ''),
        })
    return games


def get_todays_games_mls():
    """Fetch today's MLS schedule from ESPN."""
    today = datetime.now().strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard?dates={today}&limit=50"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
    except Exception as e:
        print(f"Error fetching MLS schedule: {e}")
        return []

    games = []
    for event in data.get('events', []):
        comp = event['competitions'][0]
        teams = comp['competitors']
        home = [t for t in teams if t['homeAway'] == 'home'][0]
        away = [t for t in teams if t['homeAway'] == 'away'][0]
        status = comp['status']['type']['description']

        games.append({
            'home_team': home['team']['abbreviation'],
            'away_team': away['team']['abbreviation'],
            'home_name': home['team']['displayName'],
            'away_name': away['team']['displayName'],
            'status': status,
            'game_time': event.get('date', ''),
        })
    return games
    """Build/rebuild Elo ratings from historical data."""
    db = get_db()

    print("═" * 60)
    print("BUILDING ELO RATINGS")
    print("═" * 60)

    # NBA
    print("\n📊 Loading NBA data...")
    nba_games = fetch_nba_games()
    n_nba = load_games_to_db(nba_games, db)
    print(f"  Loaded {n_nba} new NBA games ({len(nba_games)} total)")

    nba_ratings = calculate_elo_ratings('nba')
    print(f"  Calculated ratings for {len(nba_ratings)} NBA teams")

    # NHL
    print("\n🏒 Loading NHL data...")
    nhl_games = fetch_nhl_games()
    n_nhl = load_games_to_db(nhl_games, db)
    print(f"  Loaded {n_nhl} new NHL games ({len(nhl_games)} total)")

    nhl_ratings = calculate_elo_ratings('nhl')
    print(f"  Calculated ratings for {len(nhl_ratings)} NHL teams")

    # CBB
    print("\n🏀 Loading CBB data...")
    cbb_games = fetch_cbb_games()
    n_cbb = load_games_to_db(cbb_games, db)
    print(f"  Loaded {n_cbb} new CBB games ({len(cbb_games)} total)")

    cbb_ratings = calculate_elo_ratings('cbb')
    print(f"  Calculated ratings for {len(cbb_ratings)} CBB teams")

    # MLS
    print("\n⚽ Loading MLS data...")
    mls_games = fetch_mls_games()
    n_mls = load_games_to_db(mls_games, db)
    print(f"  Loaded {n_mls} new MLS games ({len(mls_games)} total)")

    mls_ratings = calculate_elo_ratings('mls')
    print(f"  Calculated ratings for {len(mls_ratings)} MLS teams")

    # Log
    db.execute("INSERT INTO build_log (league, games_loaded, seasons) VALUES (?, ?, ?)",
               ('nba', len(nba_games), '2024-25,2025-26'))
    db.execute("INSERT INTO build_log (league, games_loaded, seasons) VALUES (?, ?, ?)",
               ('nhl', len(nhl_games), '2024-25,2025-26'))
    db.execute("INSERT INTO build_log (league, games_loaded, seasons) VALUES (?, ?, ?)",
               ('cbb', len(cbb_games), '2024-25,2025-26'))
    db.execute("INSERT INTO build_log (league, games_loaded, seasons) VALUES (?, ?, ?)",
               ('mls', len(mls_games), '2025,2026'))
    db.commit()

    total = db.execute("SELECT COUNT(*) as c FROM games").fetchone()['c']
    print(f"\n✅ Build complete. {total} total games in database.")


def cmd_ratings(args):
    """Show current Elo ratings for a league."""
    league = args[0].lower() if args else 'nba'
    db = get_db()

    rows = db.execute("""
        SELECT team, rating, games_played, wins, losses
        FROM elo_ratings WHERE league = ?
        ORDER BY rating DESC
    """, (league,)).fetchall()

    if not rows:
        print(f"No ratings found for {league}. Run 'build' first.")
        return

    print(f"\n{'═' * 55}")
    print(f"  {league.upper()} ELO RATINGS (as of {datetime.now().strftime('%Y-%m-%d')})")
    print(f"{'═' * 55}")
    print(f"  {'Rank':<5} {'Team':<6} {'Elo':>7} {'Record':>10} {'Win%':>6}")
    print(f"  {'─' * 5} {'─' * 6} {'─' * 7} {'─' * 10} {'─' * 6}")

    for i, r in enumerate(rows, 1):
        gp = r['games_played']
        win_pct = r['wins'] / gp * 100 if gp > 0 else 0
        record = f"{r['wins']}-{r['losses']}"
        print(f"  {i:<5} {r['team']:<6} {r['rating']:>7.1f} {record:>10} {win_pct:>5.1f}%")


def cmd_predict(args):
    """Predict a single game."""
    if len(args) < 3:
        print("Usage: predict <league> <away_team> <home_team>")
        return

    league = args[0].lower()
    away = args[1].upper()
    home = args[2].upper()

    home_prob, away_prob = predict_game(league, away, home)

    db = get_db()
    home_row = db.execute("SELECT rating FROM elo_ratings WHERE team=? AND league=?", (home, league)).fetchone()
    away_row = db.execute("SELECT rating FROM elo_ratings WHERE team=? AND league=?", (away, league)).fetchone()

    config = ELO_CONFIG[league]
    home_elo = home_row['rating'] if home_row else config['initial_rating']
    away_elo = away_row['rating'] if away_row else config['initial_rating']

    print(f"\n{'═' * 50}")
    print(f"  ELO PREDICTION: {away} @ {home}")
    print(f"{'═' * 50}")
    print(f"  {away:<5} Elo: {away_elo:>7.1f}  →  Win: {away_prob*100:>5.1f}%")
    print(f"  {home:<5} Elo: {home_elo:>7.1f}  →  Win: {home_prob*100:>5.1f}%")
    print(f"  Home advantage: +{config['home_advantage']} Elo points")
    print(f"{'═' * 50}")


def cmd_today(args):
    """Show Elo predictions for today's games."""
    league = args[0].lower() if args else 'nba'

    if league == 'nba':
        games = get_todays_games_nba()
    elif league == 'nhl':
        games = get_todays_games_nhl()
    elif league == 'cbb':
        games = get_todays_games_cbb()
    elif league == 'mls':
        games = get_todays_games_mls()
    else:
        print(f"Unsupported league: {league}")
        return

    if not games:
        print(f"No {league.upper()} games found for today.")
        return

    db = get_db()
    rows = db.execute("SELECT team, rating FROM elo_ratings WHERE league = ?", (league,)).fetchall()
    ratings = {r['team']: r['rating'] for r in rows}

    if not ratings:
        print(f"No ratings found for {league}. Run 'build' first.")
        return

    print(f"\n{'═' * 70}")
    print(f"  {league.upper()} ELO PREDICTIONS — {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'═' * 70}")
    print(f"  {'Matchup':<30} {'Away Elo':>9} {'Home Elo':>9} {'Away%':>7} {'Home%':>7} {'Status'}")
    print(f"  {'─' * 30} {'─' * 9} {'─' * 9} {'─' * 7} {'─' * 7} {'─' * 10}")

    for g in games:
        home_prob, away_prob = predict_game(league, g['away_team'], g['home_team'], ratings)
        config = ELO_CONFIG[league]
        away_elo = ratings.get(g['away_team'], config['initial_rating'])
        home_elo = ratings.get(g['home_team'], config['initial_rating'])

        matchup = f"{g['away_team']} @ {g['home_team']}"
        print(f"  {matchup:<30} {away_elo:>9.1f} {home_elo:>9.1f} {away_prob*100:>6.1f}% {home_prob*100:>6.1f}% {g['status']}")


def cmd_update(args):
    """Fetch latest game results and recalculate ratings."""
    db = get_db()
    print("Updating with latest results...")

    # Fetch only current season
    nba_games = fetch_nba_games(seasons=["2025-26"])
    n_nba = load_games_to_db(nba_games, db)
    print(f"  NBA: {n_nba} new games")

    nhl_games = fetch_nhl_games(seasons=[("2025-26", "20251001", "20260630")])
    n_nhl = load_games_to_db(nhl_games, db)
    print(f"  NHL: {n_nhl} new games")

    cbb_games = fetch_cbb_games(seasons=[("2025-26", "20251101", "20260410")])
    n_cbb = load_games_to_db(cbb_games, db)
    print(f"  CBB: {n_cbb} new games")

    mls_games = fetch_mls_games(seasons=[("2026", "20260201", "20261115")])
    n_mls = load_games_to_db(mls_games, db)
    print(f"  MLS: {n_mls} new games")

    # Recalculate
    calculate_elo_ratings('nba')
    calculate_elo_ratings('nhl')
    calculate_elo_ratings('cbb')
    calculate_elo_ratings('mls')
    print("✅ Ratings updated.")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0].lower()
    rest = args[1:]

    commands = {
        'build': cmd_build,
        'ratings': cmd_ratings,
        'predict': cmd_predict,
        'today': cmd_today,
        'update': cmd_update,
    }

    if cmd in commands:
        commands[cmd](rest)
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
