import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime

# --- Pärkli Spiele + Schiri ---
resp = requests.get('https://foul.ch/giele/spielplan')
soup = BeautifulSoup(resp.text, 'html.parser')
spiele, schiri = [], []
for day in soup.select('li.game-day'):
    time_el = day.select_one('label time')
    if not time_el: continue
    date_attr = time_el.get('datetime', '')
    for row in day.select('tr'):
        teams_el = row.select_one('td.teams')
        if not teams_el: continue
        links = teams_el.select('a')
        if len(links) < 2: continue
        heim = links[0].get_text(strip=True)
        gast = links[1].get_text(strip=True)
        anpfiff = row.select_one('td.anpfiff time')
        tore_el = row.select_one('td.tore')
        fp_el = row.select_one('td.fairplay')
        schiri_el = row.select_one('td.schiri a')
        obj = {
            'date': date_attr,
            'zeit': anpfiff.get_text(strip=True) if anpfiff else '',
            'heim': heim, 'gast': gast,
            'tore': ' '.join(tore_el.get_text(strip=True).split()) if tore_el else '',
            'fp': ' '.join(fp_el.get_text(strip=True).split()) if fp_el else '',
            'schiri': schiri_el.get_text(strip=True) if schiri_el else ''
        }
        if 'Pärkli' in heim or 'Pärkli' in gast: spiele.append(obj)
        if schiri_el and 'Pärkli' in schiri_el.get_text(): schiri.append(obj)

with open('data-paerkli.json', 'w', encoding='utf-8') as f:
    json.dump({'spiele': spiele, 'schiri': schiri, 'updated': datetime.utcnow().isoformat()+'Z'}, f, ensure_ascii=False, indent=2)
print(f"Spiele: {len(spiele)}, Schiri: {len(schiri)}")

# --- Tabelle Liga 1 + Liga 2 ---
resp2 = requests.get('https://foul.ch/giele/tabelle')
soup2 = BeautifulSoup(resp2.text, 'html.parser')
tables = soup2.select('table')
result = {'liga1': [], 'liga2': [], 'updated': datetime.utcnow().isoformat()+'Z'}
for ti, table in enumerate(tables[:2]):
    key = 'liga' + str(ti+1)
    for ri, row in enumerate(table.select('tbody tr')):
        cells = row.select('td')
        if len(cells) < 11: continue
        link = cells[0].select_one('a')
        team = (link.get_text(strip=True) if link else cells[0].get_text(strip=True)).replace(' Chilefäud','')
        result[key].append({
            'rang': ri+1, 'team': team,
            'sp': cells[1].get_text(strip=True), 's': cells[2].get_text(strip=True),
            'n': cells[3].get_text(strip=True), 'u': cells[4].get_text(strip=True),
            'gplus': cells[5].get_text(strip=True), 'gminus': cells[6].get_text(strip=True),
            'diff': cells[7].get_text(strip=True), 'fp': cells[8].get_text(strip=True),
            'pkt': cells[11].get_text(strip=True) if len(cells)>11 else ''
        })

with open('data-tabelle.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"Tabelle L1: {len(result['liga1'])}, L2: {len(result['liga2'])}")
