import os
import json
import requests
from datetime import datetime, timezone, date
from bs4 import BeautifulSoup

# ─── Konfiguration ────────────────────────────────────────────────────────────
API_URL   = "https://foul.ch/actions/graphql/api"
TOKEN     = os.environ.get("FOUL_API_TOKEN", "").strip()
TEAM_ID   = 1689        # Pärkli Boys United
TEAM_NAME = "Pärkli"
SEASON_ID = 21052   # 2025-2026
LIGA1_ID  = 240     # Liga 1
LIGA2_ID  = 242     # Liga 2

# ─── GraphQL-Hilfsfunktion ────────────────────────────────────────────────────
def gql(query: str) -> dict:
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type":  "application/json",
    }
    resp = requests.post(API_URL, json={"query": query}, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL Fehler: {data['errors']}")
    return data["data"]

# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────
def parse_date(iso):
    return iso[:10] if iso else ""

def parse_time(iso):
    return iso[11:16] if iso and len(iso) >= 16 else ""

def fmt_score(a, b):
    if a is None or b is None:
        return ":"
    return f"{int(a)} : {int(b)}"

# ═══════════════════════════════════════════════════════════════════════════════
# 1) PÄRKLI-SPIELE & SCHIRI via API
# ═══════════════════════════════════════════════════════════════════════════════
print("🔄 Lade Pärkli-Spiele via API ...")

QUERY_PAERKLI = """
{
  entries(section: "gamesBoys", relatedToAll: [%d, %d], limit: 200, orderBy: "kickOff asc") {
    ... on gamesBoys_giele_Entry {
      kickOff
      homeTeam  { title }
      guestTeam { title }
      goalHome
      goalGuest
      fairplayHome
      fairplayGuest
      umpire    { title }
    }
  }
}
""" % (TEAM_ID, SEASON_ID)

raw = gql(QUERY_PAERKLI)["entries"]
spiele = []
for e in raw:
    heim = e["homeTeam"][0]["title"]  if e.get("homeTeam")  else ""
    gast = e["guestTeam"][0]["title"] if e.get("guestTeam") else ""
    if TEAM_NAME not in heim and TEAM_NAME not in gast:
        continue
    spiele.append({
        "date":   parse_date(e["kickOff"]),
        "zeit":   parse_time(e["kickOff"]),
        "heim":   heim,
        "gast":   gast,
        "tore":   fmt_score(e.get("goalHome"),    e.get("goalGuest")),
        "fp":     fmt_score(e.get("fairplayHome"), e.get("fairplayGuest")),
        "schiri": e["umpire"][0]["title"] if e.get("umpire") else "",
    })
print(f"   ✅ Spiele: {len(spiele)}")

QUERY_SCHIRI = """
{
  entries(section: "gamesBoys", umpire: [%d], season: [%d], limit: 100, orderBy: "kickOff asc") {
    ... on gamesBoys_giele_Entry {
      kickOff
      homeTeam  { title }
      guestTeam { title }
      goalHome
      goalGuest
    }
  }
}
""" % (TEAM_ID, SEASON_ID)

raw_s = gql(QUERY_SCHIRI)["entries"]
schiri_dienste = []
for e in raw_s:
    schiri_dienste.append({
        "date": parse_date(e["kickOff"]),
        "zeit": parse_time(e["kickOff"]),
        "heim": e["homeTeam"][0]["title"]  if e.get("homeTeam")  else "",
        "gast": e["guestTeam"][0]["title"] if e.get("guestTeam") else "",
        "tore": fmt_score(e.get("goalHome"), e.get("goalGuest")),
    })
print(f"   ✅ Schiri-Dienste: {len(schiri_dienste)}")

# ═══════════════════════════════════════════════════════════════════════════════
# 2) KOMMENDE SPIELE via Spielplan-Scraping (foul.ch/giele/spielplan)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n🔄 Scrape kommende Pärkli-Spiele vom Spielplan ...")

today_str = date.today().isoformat()

spielplan_resp = requests.get("https://foul.ch/giele/spielplan", timeout=30)
spielplan_resp.raise_for_status()
soup = BeautifulSoup(spielplan_resp.text, "html.parser")

# Liga 1 = erstes .game-schedule Element
liga1_sched = soup.select(".game-schedule")[0] if soup.select(".game-schedule") else None

kommende_spielplan = []
if liga1_sched:
    for game_day in liga1_sched.select("li.game-day"):
        time_el = game_day.select_one("time[datetime]")
        if not time_el:
            continue
        date_str = time_el["datetime"]  # z.B. "2026-05-17"
        if date_str <= today_str:
            continue  # Nur zukünftige Tage

        for row in game_day.select("tbody tr"):
            tds = row.select("td")
            if len(tds) < 5:
                continue

            zeit_el = tds[0].select_one("time")
            zeit = zeit_el["datetime"] if zeit_el and zeit_el.get("datetime") else tds[0].get_text(strip=True)

            teams = tds[1].select("a")
            if len(teams) < 2:
                continue
            heim = teams[0].get_text(strip=True)
            gast = teams[1].get_text(strip=True)

            tore_raw = tds[2].get_text(strip=True)
            schiri  = tds[4].get_text(strip=True)

            if TEAM_NAME not in heim and TEAM_NAME not in gast:
                continue  # Kein Pärkli-Spiel

            # Nur wenn noch kein Ergebnis eingetragen
            parts = [p.strip() for p in tore_raw.split(":")]
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                continue  # Schon gespielt

            kommende_spielplan.append({
                "date":   date_str,
                "zeit":   zeit,
                "heim":   heim,
                "gast":   gast,
                "tore":   ":",
                "fp":     ":",
                "schiri": schiri,
            })

print(f"   ✅ Kommende Spiele vom Spielplan: {len(kommende_spielplan)}")

# Merge: nur neue Einträge hinzufügen (Duplikat-Check)
existing_keys = {(s["date"], s["heim"], s["gast"]) for s in spiele}
for s in kommende_spielplan:
    key = (s["date"], s["heim"], s["gast"])
    if key not in existing_keys:
        spiele.append(s)
        existing_keys.add(key)

spiele.sort(key=lambda x: (x["date"], x["zeit"]))
print(f"   ✅ Total Spiele inkl. kommende: {len(spiele)}")

with open("data-paerkli.json", "w", encoding="utf-8") as f:
    json.dump(
        {"spiele": spiele, "schiri": schiri_dienste,
         "updated": datetime.now(timezone.utc).isoformat()},
        f, ensure_ascii=False, indent=2,
    )
print("   💾 data-paerkli.json gespeichert")

# ═══════════════════════════════════════════════════════════════════════════════
# 2) TABELLE via API (alle Spiele der Saison → Tabelle berechnen)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n🔄 Berechne Tabelle via API ...")

QUERY_LIGA1 = """
{
  entries(section: "gamesBoys", season: [%d], league: [%d], limit: 500, orderBy: "kickOff asc") {
    ... on gamesBoys_giele_Entry {
      homeTeam  { title }
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
      homeTeam  { title }
      guestTeam { title }
      goalHome
      goalGuest
      fairplayHome
      fairplayGuest
    }
  }
}
""" % (SEASON_ID, LIGA2_ID)

games_liga1 = gql(QUERY_LIGA1)["entries"]
games_liga2 = gql(QUERY_LIGA2)["entries"]
print(f"   📦 Liga 1: {len(games_liga1)} Spiele, Liga 2: {len(games_liga2)} Spiele")

# Tabelle berechnen
def calc_table(games):
    teams = {}

    def get(name):
        if name not in teams:
            teams[name] = {"sp": 0, "s": 0, "n": 0, "u": 0,
                           "gplus": 0, "gminus": 0, "fp": 0, "pkt": 0}
        return teams[name]

    for g in games:
        if g.get("goalHome") is None or g.get("goalGuest") is None:
            continue  # Spiel noch nicht gespielt
        heim  = g["homeTeam"][0]["title"]  if g.get("homeTeam")  else None
        gast  = g["guestTeam"][0]["title"] if g.get("guestTeam") else None
        if not heim or not gast:
            continue

        gh = int(g["goalHome"])
        gg = int(g["goalGuest"])
        fph = int(g["fairplayHome"])  if g.get("fairplayHome")  is not None else 0
        fpg = int(g["fairplayGuest"]) if g.get("fairplayGuest") is not None else 0

        h = get(heim)
        a = get(gast)

        h["sp"] += 1;  a["sp"] += 1
        h["gplus"]  += gh; h["gminus"] += gg
        a["gplus"]  += gg; a["gminus"] += gh
        h["fp"] += fph;    a["fp"] += fpg

        if gh > gg:
            h["s"] += 1; h["pkt"] += 3
            a["n"] += 1
        elif gh < gg:
            a["s"] += 1; a["pkt"] += 3
            h["n"] += 1
        else:
            h["u"] += 1; h["pkt"] += 1
            a["u"] += 1; a["pkt"] += 1

    # Sortierung: Punkte → Tordifferenz → Tore
    sorted_teams = sorted(
        teams.items(),
        key=lambda x: (x[1]["pkt"], x[1]["gplus"] - x[1]["gminus"], x[1]["gplus"]),
        reverse=True,
    )

    result = []
    for rang, (name, t) in enumerate(sorted_teams, 1):
        diff = t["gplus"] - t["gminus"]
        result.append({
            "rang":   rang,
            "team":   name.replace(" Chilefäud", ""),
            "sp":     str(t["sp"]),
            "s":      str(t["s"]),
            "n":      str(t["n"]),
            "u":      str(t["u"]),
            "gplus":  str(t["gplus"]),
            "gminus": str(t["gminus"]),
            "diff":   f"+{diff}" if diff > 0 else str(diff),
            "fp":     str(t["fp"]),
            "pkt":    str(t["pkt"]),
        })
    return result

tabelle = {
    "liga1":   calc_table(games_liga1),
    "liga2":   calc_table(games_liga2),
    "updated": datetime.now(timezone.utc).isoformat(),
}
print(f"   ✅ Liga 1: {len(tabelle['liga1'])} Teams, Liga 2: {len(tabelle['liga2'])} Teams")

with open("data-tabelle.json", "w", encoding="utf-8") as f:
    json.dump(tabelle, f, ensure_ascii=False, indent=2)
print("   💾 data-tabelle.json gespeichert")
print("\n✅ Fertig! Kein Scraping mehr — 100% API.")
