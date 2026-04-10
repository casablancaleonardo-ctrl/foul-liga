import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime

URL = 'https://foul.ch/giele/spielplan'
resp = requests.get(URL)
soup = BeautifulSoup(resp.text, 'html.parser')

spiele = []
schiri = []

for day in soup.select('li.game-day'):
    time_el = day.select_one('label time')
    if not time_el:
        continue
    date_attr = time_el.get('datetime', '')
    for row in day.select('tr'):
        teams_el = row.select_one('td.teams')
        if not teams_el:
            continue
        links = teams_el.select('a')
        if len(links) < 2:
            continue
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
        if 'Pärkli' in heim or 'Pärkli' in gast:
            spiele.append(obj)
        if schiri_el and 'Pärkli' in schiri_el.get_text():
            schiri.append(obj)

data = {'spiele': spiele, 'schiri': schiri, 'updated': datetime.utcnow().isoformat() + 'Z'}
with open('data-paerkli.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f"Fertig: {len(spiele)} Spiele, {len(schiri)} Schiri-Dienste")
