import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

rate_lock = threading.Lock()
last_request_time = [0.0]
MIN_DELAY = 1.0  # seconds between requests globally

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
})


def throttled_get(url, timeout=15):
    with rate_lock:
        elapsed = time.time() - last_request_time[0]
        if elapsed < MIN_DELAY:
            time.sleep(MIN_DELAY - elapsed)
        last_request_time[0] = time.time()
    return SESSION.get(url, timeout=timeout)

TEAMS = {
    # EAST
    "duke-blue-devils": "Duke",
    "siena-saints": "Siena",
    "ohio-state-buckeyes": "Ohio State",
    "tcu-horned-frogs": "TCU",
    "st-johns-red-storm": "St. John's",
    "northern-iowa-panthers": "Northern Iowa",
    "kansas-jayhawks": "Kansas",
    "california-baptist-lancers": "Cal Baptist",
    "louisville-cardinals": "Louisville",
    "south-florida-bulls": "South Florida",
    "michigan-state-spartans": "Michigan State",
    "north-dakota-state-bison": "North Dakota State",
    "ucla-bruins": "UCLA",
    "ucf-knights": "UCF",
    "uconn-huskies": "UConn",
    "furman-paladins": "Furman",
    # SOUTH
    "florida-gators": "Florida",
    "lehigh-mountain-hawks": "Lehigh",
    "prairie-view-panthers": "Prairie View",
    "clemson-tigers": "Clemson",
    "iowa-hawkeyes": "Iowa",
    "vanderbilt-commodores": "Vanderbilt",
    "mcneese-state-cowboys": "McNeese State",
    "nebraska-cornhuskers": "Nebraska",
    "troy-trojans": "Troy",
    "north-carolina-tar-heels": "North Carolina",
    "vcu-rams": "VCU",
    "illinois-fighting-illini": "Illinois",
    "penn-quakers": "Penn",
    "saint-marys-gaels": "Saint Mary's",
    "texas-am-aggies": "Texas A&M",
    "houston-cougars": "Houston",
    "idaho-vandals": "Idaho",
    # WEST
    "arizona-wildcats": "Arizona",
    "liu-sharks": "LIU",
    "villanova-wildcats": "Villanova",
    "utah-state-aggies": "Utah State",
    "wisconsin-badgers": "Wisconsin",
    "high-point-panthers": "High Point",
    "arkansas-razorbacks": "Arkansas",
    "hawaii-rainbow-warriors": "Hawaii",
    "byu-cougars": "BYU",
    "nc-state-wolfpack": "NC State",
    "miami-hurricanes": "Miami (FL)",
    "gonzaga-bulldogs": "Gonzaga",
    "kennesaw-state-owls": "Kennesaw State",
    "missouri-tigers": "Missouri",
    "purdue-boilermakers": "Purdue",
    "queens-royals": "Queens (NC)",
    # MIDWEST
    "michigan-wolverines": "Michigan",
    "howard-bison": "Howard",
    "umbc-retrievers": "UMBC",
    "georgia-bulldogs": "Georgia",
    "saint-louis-billikens": "Saint Louis",
    "texas-tech-red-raiders": "Texas Tech",
    "akron-zips": "Akron",
    "alabama-crimson-tide": "Alabama",
    "hofstra-pride": "Hofstra",
    "tennessee-volunteers": "Tennessee",
    "smu-mustangs": "SMU",
    "miami-redhawks": "Miami (OH)",
    "virginia-cavaliers": "Virginia",
    "wright-state-raiders": "Wright State",
    "kentucky-wildcats": "Kentucky",
    "santa-clara-broncos": "Santa Clara",
    "iowa-state-cyclones": "Iowa State",
    "tennessee-state-tigers": "Tennessee State",
}

TEAM_STATS_URL = "https://www.foxsports.com/college-basketball/{}-team-stats?category=scoring&season=2025&sort=ppg&sortOrder=desc"
GAMELOG_URL = "https://www.foxsports.com/college-basketball/{}-player-game-log?season=2025"


def extract_next_data(soup):
    """Pull data from Next.js __NEXT_DATA__ script tag if present."""
    tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if tag:
        try:
            return json.loads(tag.string)
        except Exception:
            pass
    return None


def get_players(team_slug, team_name):
    url = TEAM_STATS_URL.format(team_slug)
    try:
        r = throttled_get(url)
        r.raise_for_status()
    except Exception as e:
        print(f"  ERROR {team_name}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    # Debug: show what we got
    next_data = extract_next_data(soup)
    if next_data:
        print(f"  [Next.js data found — {len(str(next_data))} chars]")

    rows = soup.find_all("tr")
    print(f"  [HTML table rows found: {len(rows)}]")

    players = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        name_cell = cells[1]
        ppg_cell = cells[5]
        name = name_cell.get_text(strip=True)
        # Position is glued directly to name end (e.g. "Cameron BoozerF") — strip it
        name = re.sub(r'(F|G|C|G-F|F-C|F-G|C-F|PF|PG|SG|SF)$', '', name).strip()
        ppg_text = ppg_cell.get_text(strip=True)
        try:
            ppg = float(ppg_text)
        except ValueError:
            continue
        if not name or ppg <= 0:
            continue

        # Extract player slug from the link in the name cell
        player_slug = None
        link = name_cell.find("a")
        if link and link.get("href"):
            href = link["href"]
            last = href.rstrip("/").split("/")[-1]
            player_slug = last.replace("-player-stats", "")

        players.append({"Player": name, "Team": team_name, "PPG": ppg, "player_slug": player_slug})

    return players


def get_l10_ppg(player_slug):
    if not player_slug:
        return None
    url = GAMELOG_URL.format(player_slug)
    try:
        r = throttled_get(url)
        r.raise_for_status()
    except Exception as e:
        print(f"    ERROR gamelog {player_slug}: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.find_all("tr")
    points = []

    # Find PTS column index using only <td> cells in the header row,
    # so the index matches data rows (avoids off-by-one from leading <th>)
    pts_col = None
    for row in rows:
        td_texts = [td.get_text(strip=True).upper() for td in row.find_all("td")]
        if "PTS" in td_texts:
            pts_col = td_texts.index("PTS")
            break

    if pts_col is None:
        return None

    for row in rows:
        cells = row.find_all("td")
        if len(cells) <= pts_col:
            continue
        try:
            pts = int(cells[pts_col].get_text(strip=True))
            if 0 <= pts <= 75:
                points.append(pts)
        except ValueError:
            continue

    last10 = points[-10:] if len(points) >= 10 else points
    if not last10:
        return None
    return round(sum(last10) / len(last10), 1)


# Step 1: fetch all team rosters (sequential — 68 teams)
all_players = []
for team_slug, team_name in TEAMS.items():
    print(f"Scraping {team_name}...")
    players = get_players(team_slug, team_name)
    print(f"  Found {len(players)} players")
    all_players.extend(players)
    time.sleep(2)

print(f"\nTotal players found: {len(all_players)}")
print("Fetching game logs in parallel...")

# Step 2: fetch all game logs in parallel (10 workers)
def fetch_l10(player):
    slug = player.pop("player_slug")
    player["PPG_L10"] = get_l10_ppg(slug)
    return player

with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(fetch_l10, p): p for p in all_players}
    done = 0
    for future in as_completed(futures):
        future.result()
        done += 1
        if done % 50 == 0:
            print(f"  {done}/{len(all_players)} game logs fetched...")

df = pd.DataFrame(all_players)
if df.empty:
    print("No data collected.")
    print("Tip: Fox Sports may require JavaScript — check __NEXT_DATA__ output above.")
else:
    df = df[["Player", "Team", "PPG", "PPG_L10"]].sort_values("PPG", ascending=False).reset_index(drop=True)
    df.to_csv("march_madness_players.csv", index=False)
    print("\n=== TOP 30 BY PPG ===")
    print(df.head(30).to_string(index=False))
    print(f"\nTotal players: {len(df)}")
    print("Saved to march_madness_players.csv")
