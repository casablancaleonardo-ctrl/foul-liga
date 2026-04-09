import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime

def parse_table(url):
    r = requests.get(url, timeout=15)
    soup = BeautifulSoup(r.text, 'html.parser')
    result = {}
    current_liga = None
    for el in soup.find_all(['h2', 'table']):
        if el.name == 'h2':
            current_liga = el.get_text(strip=True)
            result[current_liga] = []
        elif el.name == 'table' and current_liga:
            headers = [th.get_text(strip=True) for th in el.find_all('th')]
            rows = []
            for tr in el.find_all('tr')[1:]:
                tds = tr.find_all('td')
                cols = [td.get_text(strip=True) for td in tds]
                if not cols:
                    continue
                cl = ' '.join(tr.get('class', []))
                zone = 'up' if 'aufstieg' in cl or 'zone-up' in cl else ('bar' if 'barrage' in cl or 'zone-bar' in cl else ('down' if 'abstieg' in cl or 'zone-down' in cl else ''))
                link = tds[0].find('a') if tds else None
                team = link.get_text(strip=True) if link else (cols[0] if cols else '')
                rows.append({'team': team, 'cols': cols[1:], 'zone': zone})
            result[current_liga].append({'headers': headers, 'rows': rows})
    return result

def parse_spielplan(url):
    r = requests.get(url, timeout=15)
    soup = BeautifulSoup(r.text, 'html.parser')
    spieltage = []
    for li in soup.select('main ul > li, .content ul > li, ul > li'):
        text = li.get_text(' ', strip=True)
        datum = ''
        for word in text.split():
            if len(word) == 10 and word.count('.') == 2:
                try:
                    datetime.strptime(word, '%d.%m.%Y')
                    datum = word
                    break
                except: pass
        if not datum: continue
        spiele = []
        for tr in li.find_all('tr')[1:]:
            tds = tr.find_all('td')
            if len(tds) < 3: continue
            links = tds[1].find_all('a')
            heim = links[0].get_text(strip=True) if len(links) > 0 else ''
            gast = links[1].get_text(strip=True) if len(links) > 1 else ''
            tore = tds[2].get_text(strip=True) if len(tds) > 2 else ''
            fp = tds[3].get_text(strip=True) if len(tds) > 3 else ''
            schiri = tds[4].get_text(strip=True) if len(tds) > 4 else ''
            spiele.append({
+                'anpfiff': tds[0].get_text(strip=True),
                'heim': heim, 'gast': gast,
                'tore': tore, 'fp': fp, 'schiri': schiri
            })
        if spiele: spieltage.append({'datum': datum, 'spiele': spiele})
    return spieltage

print("Scraping foul.ch...")
tabelle = parse_table('https://foul.ch/giele/tabelle')
spielplan = parse_spielplan('https://foul.ch/giele/spielplan')
letzter_spieltag = None
for st in reversed(spielplan):
    for sp in st['spiele']:
        tore = sp.get('tore','').strip()
        if tore and tore != ':' and ':' in tore:
            letzter_spieltag = st; break
    if letzter_spieltag: break
data = {'updated': datetime.now().isoformat(), 'tabelle': tabelle, 'spielplan': spielplan, 'letzter_spieltag': letzter_spieltag}
with open('data.json','w',encoding='utf-8') as f: print(f'OK. {list(tabelle.keys())}')
