import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime

TEAM_URL = 'https://foul.ch/teams/paerkli-boys-united'
SPIELPLAN_URL = 'https://foul.ch/giele/spielplan'

def parse_spielplan_team():
    r = requests.get(SPIELPLAN_URL, timeout=15)
    soup = BeautifulSoup(r.text, 'html.parser')
    gespielt = []
    kommend = []
    heute = datetime.now()

    for li in soup.select('ul > li'):
        text = li.get_text(' ', strip=True)
        datum = ''
        for word in text.split():
            if len(word) == 10 and word.count('.') == 2:
                try:
                    datetime.strptime(word, '%d.%m.%Y')
                    datum = word
                    break
                except:
                    pass
        if not datum:
            continue

        dt = datetime.strptime(datum, '%d.%m.%Y')

        for tr in li.find_all('tr')[1:]:
            tds = tr.find_all('td')
            if len(tds) < 3:
                continue
            links = tds[1].find_all('a')
            heim = links[0].get_text(strip=True) if len(links) > 0 else ''
            gast = links[1].get_text(strip=True) if len(links) > 1 else ''

            # Nur Pärkliboys-Spiele
            if 'rkli' not in heim and 'rkli' not in gast:
                continue

            tore  = tds[2].get_text(strip=True) if len(tds) > 2 else ''
            fp    = tds[3].get_text(strip=True) if len(tds) > 3 else ''
            schiri = tds[4].get_text(strip=True) if len(tds) > 4 else ''
            anpfiff = tds[0].get_text(strip=True)

            spiel = {
                'datum': datum,
                'anpfiff': anpfiff,
                'heim': heim,
                'gast': gast,
                'tore': tore,
                'fp': fp,
                'schiri': schiri
            }

            hat_resultat = ':' in tore and tore.strip() != ':'
            if hat_resultat:
                gespielt.append(spiel)
            else:
                if dt >= heute.replace(hour=0, minute=0, second=0, microsecond=0):
                    kommend.append(spiel)

    # Schiedsrichterdienste: Spiele wo PBU Schiri ist
    schiri_dienste = []
    for li in soup.select('ul > li'):
        text = li.get_text(' ', strip=True)
        datum = ''
        for word in text.split():
            if len(word) == 10 and word.count('.') == 2:
                try:
                    datetime.strptime(word, '%d.%m.%Y')
                    datum = word
                    break
                except:
                    pass
        if not datum:
            continue
        dt = datetime.strptime(datum, '%d.%m.%Y')
        if dt < heute.replace(hour=0, minute=0, second=0, microsecond=0):
            continue

        for tr in li.find_all('tr')[1:]:
            tds = tr.find_all('td')
            if len(tds) < 5:
                continue
            schiri = tds[4].get_text(strip=True)
            if 'rkli' not in schiri:
                continue
            links = tds[1].find_all('a')
            heim = links[0].get_text(strip=True) if len(links) > 0 else ''
            gast = links[1].get_text(strip=True) if len(links) > 1 else ''
            schiri_dienste.append({
                'datum': datum,
                'anpfiff': tds[0].get_text(strip=True),
                'heim': heim,
                'gast': gast,
                'schiri': schiri
            })

    return gespielt, kommend, schiri_dienste

print("Scraping Pärkliboys...")
gespielt, kommend, schiri_dienste = parse_spielplan_team()

data = {
    'updated': datetime.now().isoformat(),
    'gespielt': gespielt,
    'kommend': kommend,
    'schiri_dienste': schiri_dienste
}

with open('data_pbu.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"OK. Gespielt: {len(gespielt)}, Kommend: {len(kommend)}, Schiri-Dienste: {len(schiri_dienste)}")
