import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
SCHOOLS = [
    # EAST
    "duke", "siena", "ohio-state", "tcu", "st-johns", "northern-iowa",
    "kansas", "california-baptist", "louisville", "south-florida",
    "michigan-state", "north-dakota-state", "ucla", "ucf", "uconn", "furman",
    # SOUTH
    "florida", "lehigh", "prairie-view", "clemson", "iowa", "vanderbilt",
    "mcneese-state", "nebraska", "troy", "north-carolina", "vcu", "illinois",
    "penn", "saint-marys-ca", "texas-am", "houston", "idaho",
    # WEST
    "arizona", "liu", "villanova", "utah-state", "wisconsin", "high-point",
    "arkansas", "hawaii", "byu", "nc-state", "miami-fl", "gonzaga",
    "kennesaw-state", "missouri", "purdue", "queens-nc",
    # MIDWEST
    "michigan", "howard", "umbc", "georgia", "saint-louis", "texas-tech",
    "akron", "alabama", "hofstra", "tennessee", "smu", "miami-oh",
    "virginia", "wright-state", "kentucky", "santa-clara", "iowa-state",
    "tennessee-state",
]
BASE_URL = "https://www.sports-reference.com/cbb/schools/{}/men/2026.html"
GAMELOG_URL = "https://www.sports-reference.com/cbb/players/{}/gamelog/2026"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
def get_roster_and_ppg(school):
    url = BASE_URL.format(school)
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"  ERROR fetching {school}: {e}")
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table", {"id": "per_game"})
    if not table:
        print(f"  No per_game table found for {school}")
        return []
    players = []
    for row in table.find("tbody").find_all("tr"):
        if row.get("class") and "thead" in row.get("class"):
            continue
        name_cell = row.find("td", {"data-stat": "player"})
        pts_cell = row.find("td", {"data-stat": "pts_per_g"})
        if not name_cell or not pts_cell:
            continue
        name = name_cell.get_text(strip=True)
        ppg_text = pts_cell.get_text(strip=True)
        if not name or not ppg_text:
            continue
        player_link = name_cell.find("a")
        player_slug = player_link["href"].split("/")[3] if player_link else None
        try:
            ppg = float(ppg_text)
        except ValueError:
            continue
        players.append({
            "Player": name,
            "Team": school,
            "PPG": ppg,
            "player_slug": player_slug
        })
    return players
def get_l10_ppg(player_slug):
    if not player_slug:
        return None
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
    point_totals = []
    for row in table.find("tbody").find_all("tr"):
        if row.get("class") and "thead" in row.get("class"):
            continue
        pts_cell = row.find("td", {"data-stat": "pts"})
        if not pts_cell:
            continue
        pts_text = pts_cell.get_text(strip=True)
        if pts_text.isdigit():
            point_totals.append(int(pts_text))
    last10 = point_totals[-10:] if len(point_totals) >= 10 else point_totals
    if not last10:
        return None
    return round(sum(last10) / len(last10), 1)
# Main loop
all_players = []
for school in SCHOOLS:
    print(f"Scraping {school}...")
    players = get_roster_and_ppg(school)
    print(f"  Found {len(players)} players")
    for p in players:
        slug = p.pop("player_slug")
        time.sleep(0.8)
        p["PPG_L10"] = get_l10_ppg(slug)
    all_players.extend(players)
    time.sleep(1.5)
# Build and save dataframe
df = pd.DataFrame(all_players)[["Player", "Team", "PPG", "PPG_L10"]]
df = df[df["PPG"].notna()].sort_values("PPG", ascending=False).reset_index(drop=True)
df.to_csv("march_madness_players.csv", index=False)
print("\n=== TOP 30 BY PPG ===")
print(df.head(30).to_string(index=False))
print(f"\nTotal players scraped: {len(df)}")
print("Saved to march_madness_players.csv")
