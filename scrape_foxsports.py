import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import json

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
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


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
        r = requests.get(url, headers=HEADERS, timeout=15)
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
        name = ' '.join([w for w in name.split() if w not in ['F', 'G', 'C', 'G-F', 'F-C', 'F-G', 'C-F']])
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
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"    ERROR gamelog {player_slug}: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.find_all("tr")
    points = []

    # Find the PTS column index from header row
    pts_col = -1  # default to last column
    for row in rows:
        headers = row.find_all("th")
        if headers:
            for i, h in enumerate(headers):
                if h.get_text(strip=True).upper() == "PTS":
                    pts_col = i
                    break
            if pts_col != -1:
                break

    for row in rows:
        cells = row.find_all("td")
        if not cells:
            continue
        try:
            pts_text = cells[pts_col].get_text(strip=True)
            pts = int(pts_text)
            points.append(pts)
        except (ValueError, IndexError):
            continue

    last10 = points[-10:] if len(points) >= 10 else points
    if not last10:
        return None
    return round(sum(last10) / len(last10), 1)


# Main loop
all_players = []
for team_slug, team_name in TEAMS.items():
    print(f"Scraping {team_name}...")
    players = get_players(team_slug, team_name)
    print(f"  Found {len(players)} players")
    for p in players:
        slug = p.pop("player_slug")
        time.sleep(2)
        p["PPG_L10"] = get_l10_ppg(slug)
    all_players.extend(players)
    time.sleep(3)

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
