"""Flipradar: prøvekørsel af datakilder.

Spørger Boligsiden og Boliga om et lille udsnit data for ét postnummer
og gemmer, hvad der kommer tilbage, så dataindsamlingen kan bygges
efter de rigtige feltnavne. Bruger kun Pythons standardbibliotek.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "probe")
os.makedirs(OUT, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "da-DK,da;q=0.9",
}

since = (date.today() - timedelta(days=120)).isoformat()

TESTS = [
    ("boligsiden_api_cases",
     "https://api.boligsiden.dk/search/cases?addressTypes=condo,terraced+house,villa"
     "&zipCodes=2200&priceMax=4500000&per_page=5&page=1"),
    ("boligsiden_api_cases_simpel",
     "https://api.boligsiden.dk/search/cases?zipCodes=2200&per_page=5"),
    ("boligsiden_side_tilsalg",
     "https://www.boligsiden.dk/postnummer/2200/tilsalg"),
    ("boligsiden_side_solgt",
     "https://www.boligsiden.dk/postnummer/2200/solgte"),
    ("boliga_api_solgte",
     "https://api.boliga.dk/api/v2/sold/search/results?searchTab=1&sort=date-d&page=1"
     "&zipcodeFrom=2200&zipcodeTo=2200&salesDateMin=" + since),
    ("boliga_api_tilsalg",
     "https://api.boliga.dk/api/v2/search/results?pageSize=5&page=1&zipCodes=2200"),
]


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()
    except Exception as e:  # netværksfejl, timeout osv.
        return None, "", str(e).encode()


def first_record_list(obj, depth=0):
    """Find den første liste af objekter i et JSON-svar (typisk selve boligerne)."""
    if depth > 6:
        return None, None
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return obj, None
    if isinstance(obj, dict):
        for k, v in obj.items():
            lst, _ = first_record_list(v, depth + 1)
            if lst is not None:
                return lst, k
    return None, None


def shorten(obj, n=400):
    s = json.dumps(obj, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + " ..."


lines = [f"Flipradar prøvekørsel {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", ""]

for name, url in TESTS:
    status, ctype, body = fetch(url)
    lines.append(f"=== {name}")
    lines.append(f"URL: {url}")
    lines.append(f"Status: {status}   Type: {ctype}   Størrelse: {len(body)} bytes")
    text = body.decode("utf-8", errors="replace")
    data = None
    if "json" in ctype or text.lstrip()[:1] in "[{":
        try:
            data = json.loads(text)
        except ValueError:
            pass
    if data is None and "<html" in text[:2000].lower():
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.S)
        if m:
            try:
                data = json.loads(m.group(1))
                lines.append("Fandt indlejrede data (__NEXT_DATA__) i siden.")
            except ValueError:
                pass
        apis = sorted(set(re.findall(r'https://api\.[a-z]+\.dk/[A-Za-z0-9_/\-]+', text)))[:15]
        if apis:
            lines.append("API-adresser nævnt i siden: " + ", ".join(apis))
    if data is not None:
        with open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, default=str)
        if isinstance(data, dict):
            lines.append("Øverste felter: " + ", ".join(list(data.keys())[:30]))
        records, key = first_record_list(data)
        if records:
            lines.append(f"Fandt {len(records)} poster (under '{key}'). Felter i første post:")
            lines.append("  " + ", ".join(list(records[0].keys())[:60]))
            lines.append("Første post (forkortet): " + shorten(records[0], 1500))
        else:
            lines.append("Ingen liste af poster fundet i svaret.")
    else:
        lines.append("Svar (starten): " + text[:300].replace("\n", " "))
    lines.append("")
    time.sleep(2)  # skån serverne

summary = "\n".join(lines)
with open(os.path.join(OUT, "summary.txt"), "w", encoding="utf-8") as f:
    f.write(summary)
print(summary)
