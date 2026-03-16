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

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"
CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/mens-college-basketball"

TEAMS_TO_FIX = ["LIU", "Hawaii", "Queens", "Texas"]

ID_OVERRIDES = {
    "LIU":    "112358",
    "Hawaii": "62",
    "Queens": "2511",
    "Texas":  "251",
}


def build_espn_team_map():
    r = throttled_get(f"{BASE}/teams?limit=1000")
    if not r:
        return {}
    mapping = {}
    espn_teams = r.json()["sports"][0]["leagues"][0]["teams"]
    espn_lookup = {t["team"]["displayName"]: t["team"]["id"] for t in espn_teams}
    espn_lookup.update({t["team"]["shortDisplayName"]: t["team"]["id"] for t in espn_teams})

    for name in TEAMS_TO_FIX:
        if name in ID_OVERRIDES:
            tid = ID_OVERRIDES[name]
        else:
            search = TEAM_OVERRIDES.get(name, name)
            tid = espn_lookup.get(search)
            if not tid:
                for dn, tid2 in espn_lookup.items():
                    if search.lower() in dn.lower():
                        tid = tid2
                        break
        if tid:
            mapping[name] = tid
            print(f"  {name} -> {tid}")
        else:
            print(f"  WARNING: no ESPN match for '{name}'")
    return mapping


def get_roster(team_id, team_name):
    r = throttled_get(f"{BASE}/teams/{team_id}/roster")
    if not r:
        return []
    players = []
    for athlete in r.json().get("athletes", []):
        aid = athlete.get("id")
        name = athlete.get("displayName", "")
        if aid and name:
            players.append({"Player": name, "Team": team_name,
                            "team_id": team_id, "athlete_id": aid})
    return players


def get_ppg(athlete_id):
    r = throttled_get(f"{CORE}/seasons/2026/types/2/athletes/{athlete_id}/statistics/0")
    if not r:
        return None
    try:
        for cat in r.json().get("splits", {}).get("categories", []):
            for stat in cat.get("stats", []):
                if stat.get("name") in ("avgPoints", "pointsPerGame"):
                    return round(float(stat["value"]), 1)
    except Exception:
        pass
    return None


def get_season_points(athlete_id, team_id):
    """Compute season PPG from all completed game box scores (fallback for missing stats endpoint)."""
    r = throttled_get(f"{BASE}/teams/{team_id}/schedule?season=2026&seasontype=2")
    if not r:
        return None
    try:
        events = r.json().get("events", [])
        completed_ids = [
            e["id"] for e in events
            if e.get("competitions", [{}])[0].get("status", {}).get("type", {}).get("completed", False)
        ]
    except Exception:
        return None

    points = []
    for event_id in completed_ids:
        r2 = throttled_get(f"{BASE}/summary?event={event_id}")
        if not r2:
            continue
        try:
            for team_stats in r2.json().get("boxscore", {}).get("players", []):
                for stat_group in team_stats.get("statistics", []):
                    labels = stat_group.get("labels", [])
                    if "PTS" not in labels:
                        continue
                    pts_idx = labels.index("PTS")
                    for athlete in stat_group.get("athletes", []):
                        if str(athlete.get("athlete", {}).get("id")) == str(athlete_id):
                            try:
                                points.append(int(athlete["stats"][pts_idx]))
                            except (ValueError, TypeError, IndexError, KeyError):
                                pass
        except Exception:
            continue

    if not points:
        return None
    return round(sum(points) / len(points), 1)


def get_l10_ppg(athlete_id, team_id):
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
            for team_stats in r2.json().get("boxscore", {}).get("players", []):
                for stat_group in team_stats.get("statistics", []):
                    labels = stat_group.get("labels", [])
                    if "PTS" not in labels:
                        continue
                    pts_idx = labels.index("PTS")
                    for athlete in stat_group.get("athletes", []):
                        if str(athlete.get("athlete", {}).get("id")) == str(athlete_id):
                            try:
                                points.append(int(athlete["stats"][pts_idx]))
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
    ppg = get_ppg(aid)
    if ppg is None:
        ppg = get_season_points(aid, tid)
    p["PPG"] = ppg
    p["PPG_L10"] = get_l10_ppg(aid, tid)
    return p


# ── Main ──────────────────────────────────────────────────────────────────────
print("Building ESPN team map...")
team_map = build_espn_team_map()
print(f"Matched {len(team_map)}/{len(TEAMS_TO_FIX)} teams\n")

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
        if done % 20 == 0:
            print(f"  {done}/{len(all_players)} done...")

df = pd.DataFrame(all_players)
if df.empty or "PPG" not in df.columns:
    print("No data collected.")
else:
    df = df[["Player", "Team", "PPG", "PPG_L10"]]
    df = df[df["PPG"].notna()].sort_values("PPG", ascending=False).reset_index(drop=True)
    df.to_csv("march_madness_players.csv", index=False)
    print(df.to_string(index=False))
    print(f"\nTotal players: {len(df)}")
    print(f"PPG_L10 filled: {df['PPG_L10'].notna().sum()}")
    print("Saved to march_madness_players.csv")
