#!/usr/bin/env python3
"""
Polymarket Slug Builder — Maps team names to Polymarket market slugs.

Usage:
  python3 polymarket_slugs.py nba "Boston Celtics" "Milwaukee Bucks" 2026-03-02
  python3 polymarket_slugs.py nhl "Colorado Avalanche" "Los Angeles Kings" 2026-03-02
  python3 polymarket_slugs.py --list nba    # list all NBA abbreviations
"""
import sys
import json
from datetime import datetime

# ═══════════════════════════════════════════════════════════════
# VERIFIED TEAM ABBREVIATION MAPPINGS
# Source: Extracted from live Polymarket US API (March 2026)
# ═══════════════════════════════════════════════════════════════

TEAMS = {
    "nba": {
        # City/nickname → Polymarket abbreviation
        "hawks": "atl", "atlanta": "atl", "atlanta hawks": "atl",
        "celtics": "bos", "boston": "bos", "boston celtics": "bos",
        "nets": "bkn", "brooklyn": "bkn", "brooklyn nets": "bkn",
        "hornets": "cha", "charlotte": "cha", "charlotte hornets": "cha",
        "bulls": "chi", "chicago": "chi", "chicago bulls": "chi",
        "cavaliers": "cle", "cleveland": "cle", "cleveland cavaliers": "cle", "cavs": "cle",
        "mavericks": "dal", "dallas": "dal", "dallas mavericks": "dal", "mavs": "dal",
        "nuggets": "den", "denver": "den", "denver nuggets": "den",
        "pistons": "det", "detroit": "det", "detroit pistons": "det",
        "warriors": "gs", "golden state": "gs", "golden state warriors": "gs", "gsw": "gs",
        "rockets": "hou", "houston": "hou", "houston rockets": "hou",
        "pacers": "ind", "indiana": "ind", "indiana pacers": "ind",
        "clippers": "lac", "la clippers": "lac", "los angeles clippers": "lac", "los angeles c": "lac",
        "lakers": "lal", "la lakers": "lal", "los angeles lakers": "lal", "los angeles l": "lal",
        "grizzlies": "mem", "memphis": "mem", "memphis grizzlies": "mem",
        "heat": "mia", "miami": "mia", "miami heat": "mia",
        "bucks": "mil", "milwaukee": "mil", "milwaukee bucks": "mil",
        "timberwolves": "min", "minnesota": "min", "minnesota timberwolves": "min", "wolves": "min",
        "pelicans": "no", "new orleans": "no", "new orleans pelicans": "no", "nop": "no",
        "knicks": "ny", "new york knicks": "ny", "new york": "ny", "nyk": "ny",
        "thunder": "okc", "oklahoma city": "okc", "oklahoma city thunder": "okc",
        "magic": "orl", "orlando": "orl", "orlando magic": "orl",
        "76ers": "phi", "sixers": "phi", "philadelphia": "phi", "philadelphia 76ers": "phi",
        "suns": "pho", "phoenix": "pho", "phoenix suns": "pho", "phx": "pho",
        "trail blazers": "por", "blazers": "por", "portland": "por", "portland trail blazers": "por",
        "kings": "sac", "sacramento": "sac", "sacramento kings": "sac",
        "spurs": "sa", "san antonio": "sa", "san antonio spurs": "sa", "sas": "sa",
        "raptors": "tor", "toronto": "tor", "toronto raptors": "tor",
        "jazz": "uta", "utah": "uta", "utah jazz": "uta",
        "wizards": "was", "washington": "was", "washington wizards": "was",
    },
    "nhl": {
        "ducks": "ana", "anaheim": "ana", "anaheim ducks": "ana",
        "coyotes": "ari", "arizona": "ari", "arizona coyotes": "ari",
        "bruins": "bos", "boston": "bos", "boston bruins": "bos",
        "sabres": "buf", "buffalo": "buf", "buffalo sabres": "buf",
        "flames": "cgy", "calgary": "cgy", "calgary flames": "cgy",
        "hurricanes": "car", "carolina": "car", "carolina hurricanes": "car",
        "blackhawks": "chi", "chicago": "chi", "chicago blackhawks": "chi",
        "avalanche": "col", "colorado": "col", "colorado avalanche": "col",
        "blue jackets": "cbj", "columbus": "cbj", "columbus blue jackets": "cbj",
        "stars": "dal", "dallas": "dal", "dallas stars": "dal",
        "red wings": "det", "detroit": "det", "detroit red wings": "det",
        "oilers": "edm", "edmonton": "edm", "edmonton oilers": "edm",
        "panthers": "fla", "florida": "fla", "florida panthers": "fla",
        "kings": "la", "los angeles": "la", "los angeles kings": "la", "la kings": "la", "lak": "la",
        "wild": "min", "minnesota": "min", "minnesota wild": "min",
        "canadiens": "mon", "montreal": "mon", "montreal canadiens": "mon", "habs": "mon", "mtl": "mon",
        "predators": "nas", "nashville": "nas", "nashville predators": "nas", "nsh": "nas",
        "devils": "nj", "new jersey": "nj", "new jersey devils": "nj", "njd": "nj",
        "islanders": "nyi", "new york islanders": "nyi",
        "rangers": "nyr", "new york rangers": "nyr",
        "senators": "ott", "ottawa": "ott", "ottawa senators": "ott",
        "flyers": "phi", "philadelphia": "phi", "philadelphia flyers": "phi",
        "penguins": "pit", "pittsburgh": "pit", "pittsburgh penguins": "pit",
        "sharks": "sj", "san jose": "sj", "san jose sharks": "sj", "sjs": "sj",
        "kraken": "sea", "seattle": "sea", "seattle kraken": "sea",
        "blues": "stl", "st. louis": "stl", "st louis": "stl", "st. louis blues": "stl",
        "lightning": "tb", "tampa bay": "tb", "tampa bay lightning": "tb", "tbl": "tb",
        "maple leafs": "tor", "toronto": "tor", "toronto maple leafs": "tor",
        "canucks": "van", "vancouver": "van", "vancouver canucks": "van",
        "golden knights": "vgk", "vegas": "vgk", "vegas golden knights": "vgk",
        "capitals": "was", "washington": "was", "washington capitals": "was", "wsh": "was",
        "jets": "wpg", "winnipeg": "wpg", "winnipeg jets": "wpg",
    },
    "cbb": {
        # Major conference teams — ESPN displayAbbreviation → Polymarket slug abbreviation
        # SEC
        "alabama": "bama", "bama": "bama",
        "arkansas": "ark", "ark": "ark",
        "auburn": "aub", "aub": "aub",
        "florida": "fla", "fla": "fla",
        "georgia": "uga", "uga": "uga",
        "kentucky": "uk", "uk": "uk",
        "lsu": "lsu",
        "mississippi state": "msst", "msst": "msst",
        "missouri": "miz", "miz": "miz",
        "ole miss": "miss", "miss": "miss",
        "south carolina": "scar", "scar": "scar",
        "tennessee": "tenn", "tenn": "tenn",
        "texas": "tx", "tex": "tx", "tx": "tx",
        "texas a&m": "txam", "txam": "txam", "tam": "txam",
        "vanderbilt": "vandy", "vandy": "vandy",
        "oklahoma": "okla", "okla": "okla",
        # Big Ten
        "illinois": "ill", "ill": "ill",
        "indiana": "ind", "ind": "ind",
        "iowa": "iowa",
        "maryland": "mary", "umd": "mary",
        "michigan": "mich", "mich": "mich",
        "michigan state": "mst", "msu": "mst",
        "minnesota": "minn", "minn": "minn",
        "nebraska": "neb", "neb": "neb",
        "northwestern": "nw", "nw": "nw",
        "ohio state": "ohiost", "osu": "ohiost",
        "oregon": "ore", "ore": "ore",
        "penn state": "pennst", "psu": "pennst",
        "purdue": "pur", "pur": "pur",
        "rutgers": "rutger", "rutg": "rutger",
        "usc": "usc",
        "ucla": "ucla",
        "washington": "wash", "wash": "wash",
        "wisconsin": "wisc", "wis": "wisc",
        # ACC
        "boston college": "bc", "bc": "bc",
        "clemson": "clem", "clem": "clem",
        "duke": "duke",
        "florida state": "flst", "fsu": "flst",
        "georgia tech": "gt", "gt": "gt",
        "louisville": "lou", "lou": "lou",
        "miami": "mifl", "mifl": "mifl",
        "north carolina": "unc", "unc": "unc",
        "nc state": "ncst", "ncst": "ncst",
        "notre dame": "nd", "nd": "nd",
        "pittsburgh": "pitt", "pitt": "pitt",
        "syracuse": "syr", "syr": "syr",
        "virginia": "uva", "uva": "uva",
        "virginia tech": "vatech", "vt": "vatech",
        "wake forest": "wake", "wake": "wake",
        "smu": "smu",
        "stanford": "stan", "stan": "stan",
        "cal": "cal",
        # Big 12
        "arizona": "ariz", "ariz": "ariz",
        "arizona state": "asu", "asu": "asu",
        "baylor": "bayl", "bay": "bayl",
        "byu": "byu",
        "cincinnati": "cin", "cin": "cin",
        "colorado": "colo", "colo": "colo",
        "houston": "hou", "hou": "hou",
        "iowa state": "iast", "iast": "iast",
        "kansas": "kan", "kan": "kan", "ku": "kan",
        "kansas state": "kanst", "ksu": "kanst",
        "oklahoma state": "oklst", "okst": "oklst",
        "tcu": "tcu",
        "texas tech": "txtech", "ttu": "txtech",
        "ucf": "ucf",
        "utah": "utah",
        "west virginia": "wvu", "wvu": "wvu",
        # Big East
        "butler": "but", "but": "but",
        "connecticut": "uconn", "uconn": "uconn",
        "creighton": "crei", "crei": "crei",
        "depaul": "depaul", "dep": "depaul",
        "georgetown": "gtown", "gtown": "gtown",
        "marquette": "marq", "marq": "marq",
        "providence": "prov", "prov": "prov",
        "seton hall": "sh", "sh": "sh",
        "st. john's": "stj", "stj": "stj",
        "villanova": "vill", "nova": "vill",
        "xavier": "xav", "xav": "xav",
        # Other notables
        "gonzaga": "gonz", "gonz": "gonz",
        "memphis": "mphs", "mem": "mphs",
        "dayton": "day", "day": "day",
        "saint mary's": "stm", "stm": "stm",
        "san diego state": "sdsu", "sdsu": "sdsu",
        "new mexico": "nmx", "unm": "nmx",
    },
    "mls": {
        "atlanta united": "atl", "atl": "atl", "atlanta": "atl",
        "austin fc": "aus", "austin": "aus", "atx": "aus",
        "cf montreal": "mim", "cf montréal": "mim", "montreal": "mim", "mtl": "mim",
        "charlotte fc": "clt", "charlotte": "clt", "clt": "clt",
        "chicago fire": "chi", "chicago": "chi", "chi": "chi",
        "colorado rapids": "col", "colorado": "col", "col": "col",
        "columbus crew": "clb", "columbus": "clb", "clb": "clb",
        "dc united": "dcu", "d.c. united": "dcu", "dc": "dcu",
        "fc cincinnati": "fcc", "cincinnati": "fcc", "cin": "fcc", "fcc": "fcc",
        "fc dallas": "dal", "dallas": "dal", "dal": "dal",
        "houston dynamo": "hou", "houston": "hou", "hou": "hou",
        "inter miami": "mia", "miami": "mia", "mia": "mia",
        "la galaxy": "lag", "galaxy": "lag", "lag": "lag", "la": "lag",
        "lafc": "laf", "los angeles fc": "laf", "laf": "laf",
        "minnesota united": "min", "minnesota": "min", "min": "min",
        "nashville sc": "nas", "nashville": "nas", "nsh": "nas", "nas": "nas",
        "new england revolution": "ner", "new england": "ner", "ne": "ner", "ner": "ner",
        "new york city fc": "nyc", "nycfc": "nyc", "nyc": "nyc",
        "new york red bulls": "nyr", "red bulls": "nyr", "rbny": "nyr", "nyr": "nyr",
        "orlando city": "orl", "orlando": "orl", "orl": "orl",
        "philadelphia union": "phi", "philadelphia": "phi", "phi": "phi",
        "portland timbers": "por", "portland": "por", "por": "por",
        "real salt lake": "rsl", "rsl": "rsl",
        "san diego fc": "sdg", "san diego": "sdg", "sd": "sdg", "sdg": "sdg",
        "san jose earthquakes": "sje", "san jose": "sje", "sj": "sje", "sje": "sje",
        "seattle sounders": "sea", "seattle": "sea", "sea": "sea",
        "sporting kansas city": "skc", "kansas city": "skc", "skc": "skc",
        "st. louis city": "stl", "st louis": "stl", "stl": "stl",
        "toronto fc": "tor", "toronto": "tor", "tor": "tor",
        "vancouver whitecaps": "vwh", "vancouver": "vwh", "van": "vwh", "vwh": "vwh",
    },
}
ABBR_TO_NAME = {}
for league, teams in TEAMS.items():
    ABBR_TO_NAME.setdefault(league, {})
    seen_abbrs = {}
    for name, abbr in teams.items():
        if abbr not in seen_abbrs:
            seen_abbrs[abbr] = name
    ABBR_TO_NAME[league] = {v: k for k, v in seen_abbrs.items()}


def lookup_abbr(league: str, team_name: str) -> str | None:
    """Look up Polymarket abbreviation for a team name."""
    league = league.lower()
    team_name = team_name.lower().strip()
    mapping = TEAMS.get(league, {})
    
    # Direct lookup
    if team_name in mapping:
        return mapping[team_name]
    
    # Try partial match (team nickname only)
    for key, abbr in mapping.items():
        if team_name in key or key in team_name:
            return abbr
    
    return None


def build_slug(league: str, away: str, home: str, date: str) -> str:
    """Build a Polymarket market slug from team names and date."""
    league = league.lower()
    
    away_abbr = lookup_abbr(league, away)
    home_abbr = lookup_abbr(league, home)
    
    if not away_abbr:
        raise ValueError(f"Unknown {league.upper()} team: '{away}'. Use --list {league} to see options.")
    if not home_abbr:
        raise ValueError(f"Unknown {league.upper()} team: '{home}'. Use --list {league} to see options.")
    
    prefix = "atc" if league == "mls" else "aec"
    return f"{prefix}-{league}-{away_abbr}-{home_abbr}-{date}"


def list_teams(league: str):
    """Print all known abbreviations for a league."""
    league = league.lower()
    mapping = TEAMS.get(league)
    if not mapping:
        print(f"Unknown league: {league}")
        print(f"Available: {', '.join(TEAMS.keys())}")
        return
    
    # Deduplicate to show unique abbreviations
    seen = {}
    for name, abbr in sorted(mapping.items()):
        if abbr not in seen:
            seen[abbr] = name
    
    print(f"\n{'='*50}")
    print(f" {league.upper()} — Polymarket Abbreviations")
    print(f"{'='*50}")
    for abbr in sorted(seen.keys()):
        print(f"  {abbr:6s}  {seen[abbr]}")
    print(f"{'='*50}")
    print(f"  {len(seen)} teams\n")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    if sys.argv[1] == "--list":
        league = sys.argv[2] if len(sys.argv) > 2 else "nba"
        list_teams(league)
        return
    
    if sys.argv[1] == "--lookup":
        league = sys.argv[2]
        team = " ".join(sys.argv[3:])
        result = lookup_abbr(league, team)
        if result:
            print(f"{result}")
        else:
            print(f"NOT FOUND: '{team}' in {league.upper()}", file=sys.stderr)
            sys.exit(1)
        return
    
    if len(sys.argv) < 5:
        print("Usage: python3 polymarket_slugs.py <league> <away_team> <home_team> <YYYY-MM-DD>")
        print("       python3 polymarket_slugs.py --list <league>")
        print("       python3 polymarket_slugs.py --lookup <league> <team_name>")
        return
    
    league = sys.argv[1]
    away = sys.argv[2]
    home = sys.argv[3]
    date = sys.argv[4]
    
    try:
        slug = build_slug(league, away, home, date)
        print(slug)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
