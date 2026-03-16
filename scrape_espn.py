import requests
import pandas as pd
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
})

rate_lock = threading.Lock()
last_request_time = [0.0]

def throttled_get(url, timeout=15):
    with rate_lock:
        elapsed = time.time() - last_request_time[0]
        if elapsed < 0.4:
            time.sleep(0.4 - elapsed)
        last_request_time[0] = time.time()
    try:
        r = SESSION.get(url, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  ERROR {url[:80]}: {e}")
        return None

BASE  = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"
CORE  = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/mens-college-basketball"

# Our 68 teams → ESPN display name fragments to match against
TEAMS = [
    "Duke", "Siena", "Ohio State", "TCU", "St. John's", "Northern Iowa",
    "Kansas", "Cal Baptist", "Louisville", "South Florida",
    "Michigan State", "North Dakota State", "UCLA", "UCF", "UConn", "Furman",
    "Florida", "Lehigh", "Prairie View", "Clemson", "Iowa", "Vanderbilt",
    "McNeese State", "Nebraska", "Troy", "North Carolina", "VCU", "Illinois",
    "Penn", "Saint Mary's", "Texas A&M", "Houston", "Idaho",
    "Arizona", "LIU", "Villanova", "Utah State", "Wisconsin", "High Point",
    "Arkansas", "Hawaii", "BYU", "NC State", "Miami", "Gonzaga",
    "Kennesaw State", "Missouri", "Purdue", "Queens",
    "Michigan", "Howard", "UMBC", "Georgia", "Saint Louis", "Texas Tech",
    "Akron", "Alabama", "Hofstra", "Tennessee", "SMU", "Miami (OH)",
    "Virginia", "Wright State", "Kentucky", "Santa Clara", "Iowa State",
    "Tennessee State",
]

# Overrides for ambiguous names (e.g. two Miamis)
TEAM_OVERRIDES = {
    "Miami":         "Miami Hurricanes",
    "Miami (OH)":    "Miami (OH) RedHawks",
    "Penn":          "Pennsylvania Quakers",
    "LIU":           "LIU Sharks",
    "Queens":        "Queens Royals",
    "Cal Baptist":   "California Baptist Lancers",
    "McNeese State": "McNeese Cowboys",
    "Hawaii":        "Hawai\u02BBi Rainbow Warriors",
}


def build_espn_team_map():
    r = throttled_get(f"{BASE}/teams?limit=1000")
    if not r:
        return {}
    mapping = {}  # our name -> espn team id
    espn_teams = r.json()["sports"][0]["leagues"][0]["teams"]
    espn_lookup = {t["team"]["displayName"]: t["team"]["id"] for t in espn_teams}
    espn_lookup.update({t["team"]["shortDisplayName"]: t["team"]["id"] for t in espn_teams})

    for name in TEAMS:
        search = TEAM_OVERRIDES.get(name, name)
        tid = espn_lookup.get(search)
        if not tid:
            # fuzzy: find first display name that contains our search term
            for dn, tid2 in espn_lookup.items():
                if search.lower() in dn.lower():
                    tid = tid2
                    break
        if tid:
            mapping[name] = tid
            print(f"  {name} -> {tid}")
        else:
            print(f"  WARNING: no ESPN match for '{name}' (searched '{search}')")
    return mapping


def get_roster(team_id, team_name):
    """Return list of {Player, team_id, athlete_id, Team}"""
    r = throttled_get(f"{BASE}/teams/{team_id}/roster")
    if not r:
        return []
    data = r.json()
    players = []
    for athlete in data.get("athletes", []):
        aid = athlete.get("id")
        name = athlete.get("displayName", "")
        if aid and name:
            players.append({"Player": name, "Team": team_name,
                            "team_id": team_id, "athlete_id": aid})
    return players


def get_ppg(athlete_id):
    """Season PPG from ESPN athlete statistics (season in path)."""
    r = throttled_get(f"{CORE}/seasons/2026/types/2/athletes/{athlete_id}/statistics/0")
    if not r:
        return None
    try:
        data = r.json()
        for cat in data.get("splits", {}).get("categories", []):
            for stat in cat.get("stats", []):
                if stat.get("name") in ("avgPoints", "pointsPerGame"):
                    return round(float(stat["value"]), 1)
    except Exception:
        pass
    return None


def get_l10_ppg(athlete_id, team_id):
    """
    Compute PPG over last 10 games using team schedule + event box scores.
    """
    # Get last 10 completed game event IDs for this team
    r = throttled_get(f"{BASE}/teams/{team_id}/schedule?season=2026&seasontype=2")
    if not r:
        return None
    try:
        events = r.json().get("events", [])
        completed_ids = [
            e["id"] for e in events
            if e.get("competitions", [{}])[0].get("status", {}).get("type", {}).get("completed", False)
        ]
        last10_ids = completed_ids[-10:]
    except Exception:
        return None

    points = []
    for event_id in last10_ids:
        r2 = throttled_get(f"{BASE}/summary?event={event_id}")
        if not r2:
            continue
        try:
            box = r2.json().get("boxscore", {})
            for team_stats in box.get("players", []):
                for stat_group in team_stats.get("statistics", []):
                    labels = stat_group.get("labels", [])
                    if "PTS" not in labels:
                        continue
                    pts_idx = labels.index("PTS")
                    for athlete in stat_group.get("athletes", []):
                        if str(athlete.get("athlete", {}).get("id")) == str(athlete_id):
                            try:
                                pts = int(athlete["stats"][pts_idx])
                                points.append(pts)
                            except (ValueError, TypeError, IndexError, KeyError):
                                pass
        except Exception:
            continue

    if not points:
        return None
    last10 = points[-10:] if len(points) >= 10 else points
    return round(sum(last10) / len(last10), 1)


def enrich_player(p):
    aid = p["athlete_id"]
    tid = p["team_id"]
    p["PPG"]     = get_ppg(aid)
    p["PPG_L10"] = get_l10_ppg(aid, tid)
    return p


# ── Main ──────────────────────────────────────────────────────────────────────
print("Building ESPN team map...")
team_map = build_espn_team_map()
print(f"Matched {len(team_map)}/{len(TEAMS)} teams\n")

print("Fetching rosters...")
all_players = []
for team_name, team_id in team_map.items():
    players = get_roster(team_id, team_name)
    print(f"  {team_name}: {len(players)} players")
    all_players.extend(players)

print(f"\nTotal players: {len(all_players)}")
print("Fetching PPG + PPG_L10 in parallel (10 workers)...")

with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(enrich_player, p) for p in all_players]
    done = 0
    for f in as_completed(futures):
        f.result()
        done += 1
        if done % 100 == 0:
            print(f"  {done}/{len(all_players)} done...")

df = pd.DataFrame(all_players)
if df.empty or "PPG" not in df.columns:
    print("No data collected — check debug output above.")
else:
    df = df[["Player", "Team", "PPG", "PPG_L10"]]
    df = df[df["PPG"].notna()].sort_values("PPG", ascending=False).reset_index(drop=True)
    df.to_csv("march_madness_players.csv", index=False)
    print("\n=== TOP 30 BY PPG ===")
    print(df.head(30).to_string(index=False))
    print(f"\nTotal players: {len(df)}")
    print("Saved to march_madness_players.csv")
