import os
import sys
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timezone
from bs4 import BeautifulSoup

# ─── Konfiguration ────────────────────────────────────────────────────────────
API_URL = "https://foul.ch/actions/graphql/api"
TOKEN = os.environ.get("FOUL_API_TOKEN", "").strip()
TEAM_NAME = "Pärkli"
SEASON_ID = 21052 # 2025-2026 (nur für Tabellen-API)
LIGA1_ID = 240 # Liga 1
LIGA2_ID = 242 # Liga 2

# ─── HTTP-Session mit Retry ───────────────────────────────────────────────────
def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=10,
                  status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

session = make_session()

# ─── GraphQL-Hilfsfunktion ────────────────────────────────────────────────────
def gql(query: str) -> dict:
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    resp = session.post(API_URL, json={"query": query}, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL Fehler: {data['errors']}")
    return data["data"]

def fmt_score(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw or raw == ":":
        return ":"
    parts = [p.strip() for p in raw.split(":")]
    if len(parts) == 2:
        try:
            return f"{int(parts[0])} : {int(parts[1])}"
        except ValueError:
            pass
    return ":"

# ═══════════════════════════════════════════════════════════════════════════════
# 1) SPIELPLAN SCRAPING
# ═══════════════════════════════════════════════════════════════════════════════
print("Scrape Spielplan von foul.ch/giele/spielplan ...")

try:
    spielplan_resp = session.get("https://foul.ch/giele/spielplan", timeout=60)
    spielplan_resp.raise_for_status()
except requests.exceptions.RequestException as e:
    print(f"WARNUNG: foul.ch nicht erreichbar ({e}). Ueberspringe diesen Lauf.")
    sys.exit(0)

soup = BeautifulSoup(spielplan_resp.text, "html.parser")

schedules = soup.select(".game-schedule")
liga1_sched = schedules[0] if len(schedules) > 0 else None
liga2_sched = schedules[1] if len(schedules) > 1 else None

spiele: list = []
schiri_dienste: list = []

def scrape_schedule(sched, add_paerkli_games: bool, add_schiri: bool):
    if not sched:
        return
    for game_day in sched.select("li.game-day"):
        time_el = game_day.select_one("time[datetime]")
        if not time_el:
            continue
        date_str = time_el["datetime"]
        for row in game_day.select("tbody tr"):
            tds = row.select("td")
            if len(tds) < 5:
                continue
            zeit_el = tds[0].select_one("time")
            zeit = zeit_el.get("datetime", "") if zeit_el else tds[0].get_text(strip=True)
            team_links = tds[1].select("a")
            if len(team_links) < 2:
                continue
            heim = team_links[0].get_text(strip=True)
            gast = team_links[1].get_text(strip=True)
            tore = fmt_score(tds[2].get_text(strip=True))
            fp = fmt_score(tds[3].get_text(strip=True))
            schiri = tds[4].get_text(strip=True)
            if add_paerkli_games and (TEAM_NAME in heim or TEAM_NAME in gast):
                spiele.append({"date": date_str, "zeit": zeit, "heim": heim,
                               "gast": gast, "tore": tore, "fp": fp, "schiri": schiri})
            if add_schiri and TEAM_NAME in schiri:
                schiri_dienste.append({"date": date_str, "zeit": zeit,
                                       "heim": heim, "gast": gast, "tore": tore})

scrape_schedule(liga1_sched, add_paerkli_games=True, add_schiri=True)
scrape_schedule(liga2_sched, add_paerkli_games=False, add_schiri=True)
spiele.sort(key=lambda x: (x["date"], x["zeit"]))
schiri_dienste.sort(key=lambda x: (x["date"], x["zeit"]))
print(f" Paerkli-Spiele: {len(spiele)}")
print(f" Schiri-Dienste: {len(schiri_dienste)}")

with open("data-paerkli.json", "w", encoding="utf-8") as f:
    json.dump({"spiele": spiele, "schiri": schiri_dienste,
               "updated": datetime.now(timezone.utc).isoformat()},
              f, ensure_ascii=False, indent=2)
print(" data-paerkli.json gespeichert")

# ═══════════════════════════════════════════════════════════════════════════════
# 2) TABELLE via API
# ═══════════════════════════════════════════════════════════════════════════════
print("Berechne Tabelle via API ...")

QUERY_LIGA1 = """
{
  entries(section: "gamesBoys", season: [%d], league: [%d], limit: 500, orderBy: "kickOff asc") {
    ... on gamesBoys_giele_Entry {
      homeTeam { title }
      guestTeam { title }
      goalHome
      goalGuest
      fairplayHome
      fairplayGuest
    }
  }
}
""" % (SEASON_ID, LIGA1_ID)

QUERY_LIGA2 = """
{
  entries(section: "gamesBoys", season: [%d], league: [%d], limit: 500, orderBy: "kickOff asc") {
    ... on gamesBoys_giele_Entry {
      homeTeam { title }
      guestTeam { title }
      goalHome
      goalGuest
      fairplayHome
      fairplayGuest
    }
  }
}
""" % (SEASON_ID, LIGA2_ID)

try:
    games_liga1 = gql(QUERY_LIGA1)["entries"]
    games_liga2 = gql(QUERY_LIGA2)["entries"]
except requests.exceptions.RequestException as e:
    print(f"WARNUNG: Tabellen-API nicht erreichbar ({e}). Ueberspringe Tabellen-Update.")
    sys.exit(0)

print(f" Liga 1: {len(games_liga1)} Spiele, Liga 2: {len(games_liga2)} Spiele")

def calc_table(games):
    teams = {}
    def get(name):
        if name not in teams:
            teams[name] = {"sp": 0, "s": 0, "n": 0, "u": 0,
                           "gplus": 0, "gminus": 0, "fp": 0, "pkt": 0}
        return teams[name]
    for g in games:
        if g.get("goalHome") is None or g.get("goalGuest") is None:
            continue
        heim = g["homeTeam"][0]["title"] if g.get("homeTeam") else None
        gast = g["guestTeam"][0]["title"] if g.get("guestTeam") else None
        if not heim or not gast:
            continue
        gh = int(g["goalHome"])
        gg = int(g["goalGuest"])
        fph = int(g["fairplayHome"]) if g.get("fairplayHome") is not None else 0
        fpg = int(g["fairplayGuest"]) if g.get("fairplayGuest") is not None else 0
        h = get(heim); a = get(gast)
        h["sp"] += 1; a["sp"] += 1
        h["gplus"] += gh; h["gminus"] += gg
        a["gplus"] += gg; a["gminus"] += gh
        h["fp"] += fph; a["fp"] += fpg
        if gh > gg:
            h["s"] += 1; h["pkt"] += 3; a["n"] += 1
        elif gh < gg:
            a["s"] += 1; a["pkt"] += 3; h["n"] += 1
        else:
            h["u"] += 1; h["pkt"] += 1
            a["u"] += 1; a["pkt"] += 1
    sorted_teams = sorted(teams.items(),
        key=lambda x: (x[1]["pkt"], x[1]["gplus"] - x[1]["gminus"], x[1]["gplus"]),
        reverse=True)
    result = []
    for rang, (name, t) in enumerate(sorted_teams, 1):
        diff = t["gplus"] - t["gminus"]
        result.append({"rang": rang, "team": name.replace(" Chilefäud", ""),
                       "sp": str(t["sp"]), "s": str(t["s"]), "n": str(t["n"]),
                       "u": str(t["u"]), "gplus": str(t["gplus"]),
                       "gminus": str(t["gminus"]),
                       "diff": f"+{diff}" if diff > 0 else str(diff),
                       "fp": str(t["fp"]), "pkt": str(t["pkt"])})
    return result

tabelle = {"liga1": calc_table(games_liga1), "liga2": calc_table(games_liga2),
           "updated": datetime.now(timezone.utc).isoformat()}
print(f" Liga 1: {len(tabelle['liga1'])} Teams, Liga 2: {len(tabelle['liga2'])} Teams")

with open("data-tabelle.json", "w", encoding="utf-8") as f:
    json.dump(tabelle, f, ensure_ascii=False, indent=2)
print(" data-tabelle.json gespeichert")
print("Fertig!")
