import os
import json
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

# ─── Konfiguration ────────────────────────────────────────────────────────────
API_URL   = "https://foul.ch/actions/graphql/api"
TOKEN     = os.environ.get("FOUL_API_TOKEN", "").strip()
TEAM_ID   = 1689   # Pärkli Boys United
TEAM_NAME = "Pärkli"

# ─── GraphQL-Hilfsfunktion ────────────────────────────────────────────────────
def gql(query: str) -> dict:
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    resp = requests.post(API_URL, json={"query": query}, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL Fehler: {data['errors']}")
    return data["data"]

# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────
def parse_date(iso: str) -> str:
    """'2025-09-06T14:00:00+02:00' → '2025-09-06'"""
    return iso[:10] if iso else ""

def parse_time(iso: str) -> str:
    """'2025-09-06T14:00:00+02:00' → '14:00'"""
    return iso[11:16] if iso and len(iso) >= 16 else ""

def fmt_score(a, b) -> str:
    """None, None → ':' | 3, 1 → '3 : 1'"""
    if a is None or b is None:
        return ":"
    return f"{a} : {b}"

# ─── Spiele & Schiri via GraphQL API ──────────────────────────────────────────
print("🔄 Lade Pärkli-Spiele via API ...")

# Alle Spiele, in denen Pärkli irgendwie beteiligt ist (Heim, Gast oder Schiri)
QUERY_PAERKLI = """
{
  entries(section: "gamesBoys", relatedTo: [%d], limit: 200, orderBy: "kickOff asc") {
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
""" % TEAM_ID

raw = gql(QUERY_PAERKLI)["entries"]

spiele = []
for e in raw:
    heim = e["homeTeam"][0]["title"]  if e.get("homeTeam")  else ""
    gast = e["guestTeam"][0]["title"] if e.get("guestTeam") else ""
    # Nur Spiele, in denen Pärkli spielt (nicht reine Schiri-Einsätze)
    if TEAM_NAME not in heim and TEAM_NAME not in gast:
        continue
    schiri = e["umpire"][0]["title"] if e.get("umpire") else ""
    spiele.append({
        "date":   parse_date(e["kickOff"]),
        "zeit":   parse_time(e["kickOff"]),
        "heim":   heim,
        "gast":   gast,
        "tore":   fmt_score(e.get("goalHome"),     e.get("goalGuest")),
        "fp":     fmt_score(e.get("fairplayHome"),  e.get("fairplayGuest")),
        "schiri": schiri,
    })

print(f"   ✅ Spiele: {len(spiele)}")

# Spiele, bei denen Pärkli als Schiri eingeteilt ist
QUERY_SCHIRI = """
{
  entries(section: "gamesBoys", umpire: [%d], limit: 100, orderBy: "kickOff asc") {
    ... on gamesBoys_giele_Entry {
      kickOff
      homeTeam  { title }
      guestTeam { title }
      goalHome
      goalGuest
    }
  }
}
""" % TEAM_ID

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

with open("data-paerkli.json", "w", encoding="utf-8") as f:
    json.dump(
        {"spiele": spiele, "schiri": schiri_dienste,
         "updated": datetime.now(timezone.utc).isoformat()},
        f, ensure_ascii=False, indent=2,
    )
print("   💾 data-paerkli.json gespeichert")

# ─── Tabelle via HTML-Scraping ─────────────────────────────────────────────────
print("\n🔄 Lade Tabelle via Scraping ...")

resp2 = requests.get("https://foul.ch/giele/tabelle", timeout=30)
soup2 = BeautifulSoup(resp2.text, "html.parser")
tables = soup2.select("table")
result = {"liga1": [], "liga2": [], "updated": datetime.now(timezone.utc).isoformat()}

for ti, table in enumerate(tables[:2]):
    key = "liga" + str(ti + 1)
    for ri, row in enumerate(table.select("tbody tr")):
        cells = row.select("td")
        if len(cells) < 11:
            continue
        link = cells[0].select_one("a")
        team = (link.get_text(strip=True) if link else cells[0].get_text(strip=True)).replace(" Chilefäud", "")
        result[key].append({
            "rang":   ri + 1,
            "team":   team,
            "sp":     cells[1].get_text(strip=True),
            "s":      cells[2].get_text(strip=True),
            "n":      cells[3].get_text(strip=True),
            "u":      cells[4].get_text(strip=True),
            "gplus":  cells[5].get_text(strip=True),
            "gminus": cells[6].get_text(strip=True),
            "diff":   cells[7].get_text(strip=True),
            "fp":     cells[8].get_text(strip=True),
            "pkt":    cells[11].get_text(strip=True) if len(cells) > 11 else "",
        })

with open("data-tabelle.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"   ✅ Liga 1: {len(result['liga1'])} Teams, Liga 2: {len(result['liga2'])} Teams")
print("   💾 data-tabelle.json gespeichert")
print("\n✅ Fertig!")
