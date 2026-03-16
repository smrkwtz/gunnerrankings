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
}

ROSTER_URL = "https://www.sports-reference.com/cbb/schools/{}/men/2026.html"
GAMELOG_URL = "https://www.sports-reference.com/cbb/players/{}/gamelog/2026"


def get_player_slugs(school_slug):
    """Returns {normalized_name: player_slug} for all players on a roster."""
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
        return {}
    slugs = {}
    for row in table.find("tbody").find_all("tr"):
        if row.get("class") and "thead" in row.get("class"):
            continue
        name_cell = row.find("td", {"data-stat": "player"})
        if not name_cell:
            continue
        link = name_cell.find("a")
        if not link:
            continue
        name = name_cell.get_text(strip=True).lower()
        slug = link["href"].split("/")[3]
        slugs[name] = slug
    return slugs


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

# Cache slugs per team so we only fetch each roster once
roster_cache = {}

l10_values = []
for _, row in df.iterrows():
    team = row["Team"]
    player_name = row["Player"]
    school_slug = TEAM_TO_SLUG.get(team)

    if not school_slug:
        print(f"  No slug mapping for team: {team}")
        l10_values.append(None)
        continue

    if school_slug not in roster_cache:
        print(f"Fetching roster for {team}...")
        roster_cache[school_slug] = get_player_slugs(school_slug)
        time.sleep(1.5)

    slugs = roster_cache[school_slug]
    player_slug = slugs.get(player_name.lower())

    if not player_slug:
        print(f"  No slug found for {player_name} ({team})")
        l10_values.append(None)
        continue

    print(f"  {player_name} -> {player_slug}")
    l10 = get_l10_ppg(player_slug)
    l10_values.append(l10)
    time.sleep(0.8)

df["PPG_L10"] = l10_values
df.to_csv("march_madness_players.csv", index=False)

print("\n=== TOP 30 BY PPG ===")
print(df.head(30).to_string(index=False))
print(f"\nTotal players: {len(df)}")
print(f"PPG_L10 filled: {df['PPG_L10'].notna().sum()}")
print("Saved to march_madness_players.csv")
