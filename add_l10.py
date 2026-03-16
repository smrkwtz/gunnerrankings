import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Map CSV team names -> Sports Reference school slugs
TEAM_TO_SLUG = {
    "Duke": "duke",
    "Siena": "siena",
    "Ohio State": "ohio-state",
    "TCU": "tcu",
    "St. John's": "st-johns",
    "Northern Iowa": "northern-iowa",
    "Kansas": "kansas",
    "Cal Baptist": "california-baptist",
    "Louisville": "louisville",
    "South Florida": "south-florida",
    "Michigan State": "michigan-state",
    "North Dakota State": "north-dakota-state",
    "UCLA": "ucla",
    "UCF": "ucf",
    "UConn": "uconn",
    "Furman": "furman",
    "Florida": "florida",
    "Lehigh": "lehigh",
    "Prairie View": "prairie-view",
    "Clemson": "clemson",
    "Iowa": "iowa",
    "Vanderbilt": "vanderbilt",
    "McNeese State": "mcneese-state",
    "Nebraska": "nebraska",
    "Troy": "troy",
    "North Carolina": "north-carolina",
    "VCU": "vcu",
    "Illinois": "illinois",
    "Penn": "penn",
    "Saint Mary's": "saint-marys-ca",
    "Texas A&M": "texas-am",
    "Houston": "houston",
    "Idaho": "idaho",
    "Arizona": "arizona",
    "LIU": "liu",
    "Villanova": "villanova",
    "Utah State": "utah-state",
    "Wisconsin": "wisconsin",
    "High Point": "high-point",
    "Arkansas": "arkansas",
    "Hawaii": "hawaii",
    "BYU": "byu",
    "NC State": "nc-state",
    "Miami (FL)": "miami-fl",
    "Gonzaga": "gonzaga",
    "Kennesaw State": "kennesaw-state",
    "Missouri": "missouri",
    "Purdue": "purdue",
    "Queens": "queens-nc",
    "Michigan": "michigan",
    "Howard": "howard",
    "UMBC": "umbc",
    "Georgia": "georgia",
    "Saint Louis": "saint-louis",
    "Texas Tech": "texas-tech",
    "Akron": "akron",
    "Alabama": "alabama",
    "Hofstra": "hofstra",
    "Tennessee": "tennessee",
    "SMU": "smu",
    "Miami (OH)": "miami-oh",
    "Virginia": "virginia",
    "Wright State": "wright-state",
    "Kentucky": "kentucky",
    "Santa Clara": "santa-clara",
    "Iowa State": "iowa-state",
    "Tennessee State": "tennessee-state",
    "Texas": "texas",
}

# Only process these teams — all 4 are missing from the CSV entirely
TEAMS_TO_FIX = {"LIU", "Hawaii", "Queens", "Texas"}

ROSTER_URL = "https://www.sports-reference.com/cbb/schools/{}/men/2026.html"
GAMELOG_URL = "https://www.sports-reference.com/cbb/players/{}/gamelog/2026"


def get_player_data(school_slug):
    """Returns {normalized_name: {"slug": ..., "ppg": ...}} from the per-game table."""
    url = ROSTER_URL.format(school_slug)
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"  ERROR fetching roster for {school_slug}: {e}")
        return {}
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table", {"id": "per_game"})
    if not table:
        print(f"  No per_game table found for {school_slug}")
        return {}
    players = {}
    for row in table.find("tbody").find_all("tr"):
        if row.get("class") and "thead" in row.get("class"):
            continue
        name_cell = row.find("td", {"data-stat": "player"})
        if not name_cell:
            continue
        link = name_cell.find("a")
        if not link:
            continue
        name = name_cell.get_text(strip=True)
        slug = link["href"].split("/")[3]
        ppg_cell = row.find("td", {"data-stat": "pts_per_g"})
        ppg = None
        if ppg_cell:
            try:
                ppg = float(ppg_cell.get_text(strip=True))
            except ValueError:
                pass
        players[name.lower()] = {"name": name, "slug": slug, "ppg": ppg}
    return players


def get_l10_ppg(player_slug):
    url = GAMELOG_URL.format(player_slug)
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"    ERROR fetching gamelog for {player_slug}: {e}")
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table", {"id": "gamelog"})
    if not table:
        return None
    points = []
    for row in table.find("tbody").find_all("tr"):
        if row.get("class") and "thead" in row.get("class"):
            continue
        pts_cell = row.find("td", {"data-stat": "pts"})
        if not pts_cell:
            continue
        pts_text = pts_cell.get_text(strip=True)
        if pts_text.isdigit():
            points.append(int(pts_text))
    last10 = points[-10:] if len(points) >= 10 else points
    if not last10:
        return None
    return round(sum(last10) / len(last10), 1)


# Load existing CSV
df = pd.read_csv("march_madness_players.csv")
print(f"Loaded {len(df)} players from CSV")

new_rows = []

for team in TEAMS_TO_FIX:
    school_slug = TEAM_TO_SLUG.get(team)
    if not school_slug:
        print(f"No slug mapping for team: {team}")
        continue

    # Drop any existing (likely empty/stale) rows for this team
    df = df[df["Team"] != team]

    print(f"\nFetching roster for {team} ({school_slug})...")
    player_data = get_player_data(school_slug)
    time.sleep(1.5)

    if not player_data:
        print(f"  No players found for {team}")
        continue

    for norm_name, info in player_data.items():
        if info["ppg"] is None:
            print(f"  Skipping {info['name']} — no PPG")
            continue
        print(f"  {info['name']} (PPG: {info['ppg']}) -> {info['slug']}")
        l10 = get_l10_ppg(info["slug"])
        new_rows.append({
            "Player": info["name"],
            "Team": team,
            "PPG": info["ppg"],
            "PPG_L10": l10,
        })
        time.sleep(0.8)

if new_rows:
    new_df = pd.DataFrame(new_rows)
    df = pd.concat([df, new_df], ignore_index=True)
    df = df.sort_values("PPG", ascending=False).reset_index(drop=True)
    print(f"\nAdded {len(new_rows)} new player rows")

df.to_csv("march_madness_players.csv", index=False)

print("\n=== TOP 30 BY PPG ===")
print(df.head(30).to_string(index=False))
print(f"\nTotal players: {len(df)}")
print(f"PPG_L10 filled: {df['PPG_L10'].notna().sum()}")
print("Saved to march_madness_players.csv")
