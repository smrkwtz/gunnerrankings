import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

# Fox Sports slugs for all 68 teams
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

BASE_URL = "https://www.foxsports.com/college-basketball/{}-team-stats?category=scoring&season=2025&sort=ppg&sortOrder=desc"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def get_players(slug, team_name):
    url = BASE_URL.format(slug)
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"  ERROR {team_name}: {e}")
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.find_all("tr")
    players = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        name_cell = cells[1]
        ppg_cell = cells[5]
        name = name_cell.get_text(strip=True)
        # Strip position suffix
        name = ' '.join([w for w in name.split() if w not in ['F','G','C','G-F','F-C','F-G','C-F']])
        ppg_text = ppg_cell.get_text(strip=True)
        try:
            ppg = float(ppg_text)
        except ValueError:
            continue
        if name and ppg > 0:
            players.append({"Player": name, "Team": team_name, "PPG": ppg})
    return players

all_players = []
for slug, name in TEAMS.items():
    print(f"Scraping {name}...")
    players = get_players(slug, name)
    print(f"  Found {len(players)} players")
    all_players.extend(players)
    time.sleep(1.5)

df = pd.DataFrame(all_players)
if df.empty:
    print("No data collected — Fox Sports may require JavaScript rendering")
    print("Falling back to Sports Reference...")
    import subprocess
    subprocess.run(["python", "scrape_stats.py"], check=True)
else:
    df = df[["Player", "Team", "PPG"]].sort_values("PPG", ascending=False).reset_index(drop=True)
    df.to_csv("march_madness_players.csv", index=False)
    print("\n=== TOP 30 BY PPG ===")
    print(df.head(30).to_string(index=False))
    print(f"\nTotal players: {len(df)}")
    print("Saved to march_madness_players.csv")
