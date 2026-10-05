"""Flipradar: dataindsamling.

Henter boliger til salg fra Boligsiden og frie handler fra Boliga, og
beregner for hver bolig et markedsniveau ud fra sammenlignelige handler
(seneste 4 måneder) vejet mod aktuelle annoncer i nærheden.
Resultatet gemmes i data/listings.json, som Flipradar-siden læser.
Bruger kun Pythons standardbibliotek.
"""
import json
import math
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT_FILE = os.path.join(ROOT, "data", "listings.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "da-DK,da;q=0.9",
}

# ---------- Indstillinger ----------
MAX_PRICE = 4_500_000      # boliger til salg op til denne pris
SALES_DAYS = 120           # handler fra de seneste 4 måneder
FALLBACK_DAYS = 180        # bruges kun, hvis der er for få handler
MIN_COMPS = 8              # mindst så mange handler før tallet regnes som solidt
# Søgetrin: (dage tilbage, radius i meter). Første trin med nok handler bruges.
STEPS = [(SALES_DAYS, 500), (SALES_DAYS, 1000), (SALES_DAYS, 1500),
         (FALLBACK_DAYS, 1500), (FALLBACK_DAYS, 2500)]
LISTING_WEIGHT = 0.5       # en aktuel annonce vejer halvt så meget som en handel
LISTING_WEIGHT_OLD = 0.25  # annoncer der har ligget over 90 dage vejer endnu mindre

# Postnumre hos Boliga (fra-til)
ZIP_RANGES = [(1000, 2000), (2100, 2100), (2150, 2150), (2200, 2200), (2300, 2300),
              (2400, 2400), (2450, 2450), (2500, 2500), (2700, 2700), (2720, 2720)]

ZONES = [
    ("k1", "Kbh K", "Indre By", 55.6800, 12.5770), ("k2", "Kbh K", "Christianshavn", 55.6727, 12.5940),
    ("k3", "Kbh K", "Nansensgade-kvarteret", 55.6850, 12.5640),
    ("o1", "Kbh Ø", "Kartoffelrækkerne og Søerne", 55.6935, 12.5770), ("o2", "Kbh Ø", "Østerbro centrum", 55.7005, 12.5760),
    ("o3", "Kbh Ø", "Nordhavn", 55.7085, 12.5950), ("o4", "Kbh Ø", "Ryparken", 55.7170, 12.5610),
    ("n1", "Kbh N", "Sankt Hans Torv og Søerne", 55.6905, 12.5630), ("n2", "Kbh N", "Jægersborggade og Assistens", 55.6950, 12.5470),
    ("n3", "Kbh N", "Mimersgade-kvarteret", 55.6985, 12.5520), ("n4", "Kbh N", "Ydre Nørrebro", 55.7005, 12.5400),
    ("v1", "Kbh V", "Kødbyen og Istedgade", 55.6700, 12.5590), ("v2", "Kbh V", "Carlsberg Byen", 55.6655, 12.5330),
    ("v3", "Kbh V", "Saxogade og Vesterbro vest", 55.6700, 12.5450),
    ("f1", "Frederiksberg", "Gl. Kongevej og Søerne", 55.6770, 12.5480), ("f2", "Frederiksberg", "Frederiksberg Have", 55.6760, 12.5250),
    ("f3", "Frederiksberg", "Fasanvej og Nordre", 55.6875, 12.5240),
    ("s1", "Kbh S", "Islands Brygge", 55.6650, 12.5800), ("s2", "Kbh S", "Amagerbro", 55.6630, 12.5990),
    ("s3", "Kbh S", "Sundby", 55.6600, 12.6170), ("s4", "Kbh S", "Ørestad", 55.6300, 12.5770),
    ("sv1", "Kbh SV", "Sluseholmen", 55.6440, 12.5450), ("sv2", "Kbh SV", "Sydhavn", 55.6510, 12.5400),
    ("nv1", "Kbh NV", "Bispebjerg", 55.7080, 12.5350), ("nv2", "Kbh NV", "Nordvest centrum", 55.7020, 12.5300),
    ("nv3", "Kbh NV", "Utterslev", 55.7135, 12.5180),
    ("va1", "Valby", "Valby centrum", 55.6620, 12.5160), ("va2", "Valby", "Valby Langgade vest", 55.6605, 12.4950),
    ("va3", "Valby", "Vigerslev", 55.6500, 12.5050),
    ("vl1", "Vanløse", "Vanløse centrum", 55.6870, 12.4910), ("vl2", "Vanløse", "Grøndalsvænge og Damhus", 55.6810, 12.4800),
    ("vl3", "Vanløse", "Jydeholmen", 55.6935, 12.4750),
    ("b1", "Brønshøj/Husum", "Brønshøj Torv", 55.7050, 12.4950), ("b2", "Brønshøj/Husum", "Husum", 55.7110, 12.4650),
]

TYPE_MAP = {"condo": "Ejerlejlighed", "terraced house": "Rækkehus", "villa": "Villa"}
GROUP = {"Ejerlejlighed": "lejl", "Rækkehus": "hus", "Villa": "hus"}
BOLIGA_GROUP = {3: "lejl", 9: "lejl", 1: "hus", 2: "hus"}

NOW = datetime.now(timezone.utc)


def log(*a):
    print(*a, flush=True)


def get_json(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # netværksfejl, blokering, ugyldig JSON
            log(f"  Forsøg {i + 1} fejlede: {e}")
            time.sleep(3 * (i + 1))
    return None


def district(zip_code):
    try:
        z = int(zip_code)
    except (TypeError, ValueError):
        return None
    if 1000 <= z <= 1499:
        return "Kbh K"
    if 1500 <= z <= 1799:
        return "Kbh V"
    if 1800 <= z <= 2000:
        return "Frederiksberg"
    return {2100: "Kbh Ø", 2150: "Kbh Ø", 2200: "Kbh N", 2300: "Kbh S", 2400: "Kbh NV",
            2450: "Kbh SV", 2500: "Valby", 2700: "Brønshøj/Husum", 2720: "Vanløse"}.get(z)


def dist_m(lat1, lon1, lat2, lon2):
    dy = (lat2 - lat1) * 110_540
    dx = (lon2 - lon1) * 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def nearest_zone(d, lat, lon):
    best, bd = None, 1e12
    for zid, zd, _, zlat, zlon in ZONES:
        if zd != d:
            continue
        dd = dist_m(lat, lon, zlat, zlon)
        if dd < bd:
            best, bd = zid, dd
    return best


def quantile(values, q):
    v = sorted(values)
    if not v:
        return None
    pos = (len(v) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


# ---------- Boligsiden: boliger til salg ----------
def floor_text(floor, door):
    f = "" if floor is None else str(floor).strip()
    if f == "":
        part = ""
    elif f == "0":
        part = "st."
    elif f in ("-1", "kl"):
        part = "kl."
    else:
        part = f + "."
    if door:
        part = (part + " " + str(door)).strip()
    return part


def pick_image(img, width=600):
    srcs = (img or {}).get("imageSources") or []
    for s in srcs:
        if (s.get("size") or {}).get("width") == width:
            return s.get("url")
    return srcs[-1].get("url") if srcs else None


def parse_case(c):
    a = c.get("address") or {}
    zip_code = a.get("zipCode") or (a.get("zip") or {}).get("zipCode")
    d = district(zip_code)
    typ = TYPE_MAP.get(c.get("addressType") or a.get("addressType"))
    price, area = c.get("priceCash"), c.get("housingArea") or a.get("livingArea")
    coords = c.get("coordinates") or a.get("coordinates") or {}
    if not (d and typ and price and area and coords.get("lat")):
        return None
    street = f"{a.get('roadName', '')} {a.get('houseNumber', '')}".strip()
    fl = floor_text(a.get("floor"), a.get("door"))
    buildings = a.get("buildings") or []
    roofs = " ".join(str(b.get("roofingMaterial") or "") for b in buildings)
    regs = [r for r in (a.get("registrations") or []) if r.get("amount") and r.get("date")]
    regs.sort(key=lambda r: r["date"], reverse=True)
    tom = ((c.get("timeOnMarket") or {}).get("total") or {}).get("days")
    lat, lon = coords["lat"], coords["lon"]
    return {
        "id": c.get("caseID"),
        "adresse": street + (", " + fl if fl else ""),
        "postnr": zip_code,
        "by": a.get("cityName") or "",
        "distrikt": d,
        "zone": nearest_zone(d, lat, lon),
        "type": typ,
        "gruppe": GROUP[typ],
        "pris": price,
        "m2": area,
        "m2pris": round(price / area),
        "vaer": c.get("numberOfRooms"),
        "etage": a.get("floor"),
        "byggeaar": c.get("yearBuilt"),
        "energi": (c.get("energyLabel") or "").upper() or None,
        "ejerudgift": c.get("monthlyExpense") or 0,
        "liggetid": tom if tom is not None else c.get("daysOnMarket") or 0,
        "prisaendring": c.get("priceChangePercentage") or 0,
        "altan": bool(c.get("hasBalcony")),
        "elevator": bool(c.get("hasElevator")),
        "terrasse": bool(c.get("hasTerrace")),
        "asbest": "asbest" in roofs.lower(),
        "titel": c.get("descriptionTitle") or "",
        "beskrivelse": c.get("descriptionBody") or "",
        "lat": lat,
        "lng": lon,
        "url": c.get("caseUrl") or "",
        "billede": pick_image(c.get("defaultImage")),
        "plantegning": pick_image((c.get("floorPlanImages") or [None])[0], 1440),
        "tidligereSalg": [{"dato": r["date"], "pris": r["amount"]} for r in regs[:4]],
    }


def fetch_listings_query(params, label):
    cases, page, total = [], 1, None
    while page <= 80:
        q = dict(params, priceMax=MAX_PRICE, per_page=50, page=page)
        url = "https://api.boligsiden.dk/search/cases?" + urllib.parse.urlencode(q)
        data = get_json(url)
        if data is None:
            log(f"  {label}: ingen svar på side {page}")
            break
        batch = data.get("cases") or []
        total = data.get("totalHits", total)
        cases.extend(batch)
        if not batch or len(cases) >= (total or 0):
            break
        page += 1
        time.sleep(1)
    return cases, total


def fetch_listings():
    log("Henter boliger fra Boligsiden ...")
    types = "condo,terraced house,villa"
    cases, total = fetch_listings_query(
        {"addressTypes": types, "municipalities": "koebenhavn,frederiksberg"}, "kommuner")
    inside = sum(1 for c in cases if district((c.get("address") or {}).get("zipCode")))
    log(f"  Søgning på kommuner: {len(cases)} boliger hentet af {total}, {inside} i vores områder")
    if not cases or total is None or total > 8000 or inside < 0.7 * len(cases):
        log("  Kommunesøgningen så forkert ud, henter i stedet pr. postnummer ...")
        cases = []
        for lo, hi in ZIP_RANGES:
            zips = [str(z) for z in range(lo, hi + 1)]
            for i in range(0, len(zips), 60):
                part, _ = fetch_listings_query(
                    {"addressTypes": types, "zipCodes": ",".join(zips[i:i + 60])}, f"{lo}-{hi}")
                cases.extend(part)
    out, seen = [], set()
    for c in cases:
        p = parse_case(c)
        if p and p["id"] not in seen and p["pris"] <= MAX_PRICE:
            seen.add(p["id"])
            out.append(p)
    log(f"  {len(out)} boliger til salg under {MAX_PRICE:,} kr. i vores områder".replace(",", "."))
    return out


# ---------- Boliga: solgte boliger ----------
def parse_sale(r):
    group = BOLIGA_GROUP.get(r.get("propertyType"))
    if not group or r.get("saleType") != "Alm. Salg":
        return None
    size, price, sqm = r.get("size") or 0, r.get("price") or 0, r.get("sqmPrice") or 0
    if size < 15 or not price or not (15_000 <= sqm <= 250_000):
        return None
    if r.get("latitude") is None or r.get("longitude") is None:
        return None
    try:
        sold = datetime.fromisoformat(r["soldDate"].replace("Z", "+00:00")) + timedelta(hours=3)
    except (KeyError, ValueError):
        return None
    d = district(r.get("zipCode"))
    if not d:
        return None
    return {
        "adresse": r.get("address"),
        "postnr": r.get("zipCode"),
        "distrikt": d,
        "zone": nearest_zone(d, r["latitude"], r["longitude"]),
        "gruppe": group,
        "pris": price,
        "m2": size,
        "m2pris": round(sqm),
        "dato": sold.date().isoformat(),
        "alder": (NOW - sold).days,
        # Afslag ift. udbudsprisen kendes kun, når boligen har været annonceret
        "afslag": r.get("change") if r.get("estateId") else None,
        "lat": r["latitude"],
        "lng": r["longitude"],
    }


def fetch_sales():
    log("Henter frie handler fra Boliga ...")
    since = (NOW - timedelta(days=FALLBACK_DAYS)).date().isoformat()
    sales, raw = [], 0
    for lo, hi in ZIP_RANGES:
        page = 1
        while page <= 80:
            url = ("https://api.boliga.dk/api/v2/sold/search/results?searchTab=1&sort=date-d"
                   f"&page={page}&zipcodeFrom={lo}&zipcodeTo={hi}&salesDateMin={since}")
            data = get_json(url)
            if data is None:
                log(f"  {lo}-{hi}: ingen svar på side {page}")
                break
            results = data.get("results") or []
            raw += len(results)
            for r in results:
                s = parse_sale(r)
                if s and s["alder"] <= FALLBACK_DAYS:
                    sales.append(s)
            if not results or page >= (data.get("meta") or {}).get("totalPages", 1):
                break
            page += 1
            time.sleep(1)
    log(f"  {raw} handler i alt, heraf {len(sales)} almindelige frie handler af lejligheder og huse")
    return sales


# ---------- Markedsniveau ----------
def market_for(l, sales, listings, fallback_afslag):
    g, m2 = l["gruppe"], l["m2"]
    lo, hi = (0.7, 1.3) if g == "lejl" else (0.6, 1.5)
    cand = [(dist_m(l["lat"], l["lng"], s["lat"], s["lng"]), s)
            for s in sales if s["gruppe"] == g and lo * m2 <= s["m2"] <= hi * m2]
    sel, days, radius = [], STEPS[-1][0], STEPS[-1][1]
    for days, radius in STEPS:
        sel = [(dd, s) for dd, s in cand if dd <= radius and s["alder"] <= days]
        if len(sel) >= MIN_COMPS:
            break
    sel.sort(key=lambda x: x[0])
    vals = [s["m2pris"] for _, s in sel]
    sale_med = statistics.median(vals) if vals else None

    disc = [s["afslag"] for _, s in sel if s["afslag"] is not None]
    afslag = statistics.median(disc) if len(disc) >= 5 else fallback_afslag.get(g, -3.0)
    afslag = max(-15.0, min(5.0, afslag))

    others = []
    for o in listings:
        if o["id"] == l["id"] or o["gruppe"] != g or not (lo * m2 <= o["m2"] <= hi * m2):
            continue
        if dist_m(l["lat"], l["lng"], o["lat"], o["lng"]) <= radius:
            w = LISTING_WEIGHT_OLD if o["liggetid"] > 90 else LISTING_WEIGHT
            others.append((o["m2pris"] * (1 + afslag / 100), w))
    list_med = statistics.median([v for v, _ in others]) if others else None
    w_sales, w_list = float(len(vals)), sum(w for _, w in others)

    if sale_med is None and list_med is None:
        level = None
    elif list_med is None:
        level = sale_med
    elif sale_med is None:
        level = list_med
    else:
        level = (sale_med * w_sales + list_med * w_list) / (w_sales + w_list)

    return {
        "niveau": round(level) if level else None,
        "salgMedian": round(sale_med) if sale_med else None,
        "salgP75": round(quantile(vals, 0.75)) if len(vals) >= 4 else None,
        "salgAntal": len(vals),
        "dage": days,
        "radius": radius,
        "solid": len(vals) >= MIN_COMPS and days == SALES_DAYS,
        "udbudMedian": round(list_med) if list_med else None,
        "udbudAntal": len(others),
        "afslag": round(afslag, 1),
        "vaegtSalg": round(w_sales / (w_sales + w_list), 2) if (w_sales + w_list) else None,
        "handler": [{"a": s["adresse"], "d": s["dato"], "p": s["pris"], "m2": s["m2"],
                     "kvm": s["m2pris"], "afst": round(dd)} for dd, s in sel[:10]],
    }


def zone_stats(sales):
    recent = [s for s in sales if s["gruppe"] == "lejl" and s["alder"] <= SALES_DAYS]
    zones = []
    for zid, d, name, lat, lon in ZONES:
        vals = [s["m2pris"] for s in recent if s["zone"] == zid]
        zones.append({"id": zid, "d": d, "n": name, "lat": lat, "lng": lon,
                      "m2": round(statistics.median(vals)) if vals else None, "antal": len(vals)})
    for d in {z["d"] for z in zones}:
        zs = sorted([z for z in zones if z["d"] == d and z["m2"]], key=lambda z: -z["m2"])
        for i, z in enumerate(zs):
            z["autoRank"] = 1 if len(zs) == 1 else 1 + round(9 * i / (len(zs) - 1))
        for z in zones:
            if z["d"] == d and not z.get("m2"):
                z["autoRank"] = 10
    return zones


def main():
    listings = fetch_listings()
    sales = fetch_sales()
    if not listings or not sales:
        log("Mangler data fra en af kilderne. Den gamle datafil bevares.")
        sys.exit(1)

    recent = [s for s in sales if s["alder"] <= SALES_DAYS and s["afslag"] is not None]
    fallback = {}
    for g in ("lejl", "hus"):
        v = [s["afslag"] for s in recent if s["gruppe"] == g]
        fallback[g] = statistics.median(v) if v else -3.0
    log(f"Typisk afslag ift. udbudspris: lejligheder {fallback['lejl']:.1f} %, huse {fallback['hus']:.1f} %")

    for l in listings:
        l["marked"] = market_for(l, sales, listings, fallback)
    solid = sum(1 for l in listings if l["marked"]["solid"])
    log(f"Markedsniveau beregnet: {solid} af {len(listings)} boliger har mindst {MIN_COMPS} handler fra de seneste {SALES_DAYS} dage")

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    data = {
        "opdateret": NOW.isoformat(timespec="minutes"),
        "regler": {"maxPris": MAX_PRICE, "dage": SALES_DAYS, "minHandler": MIN_COMPS,
                   "annonceVaegt": LISTING_WEIGHT, "annonceVaegtGammel": LISTING_WEIGHT_OLD},
        "antalHandler": sum(1 for s in sales if s["alder"] <= SALES_DAYS),
        "zoner": zone_stats(sales),
        "boliger": listings,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    log(f"Gemt: {OUT_FILE} ({os.path.getsize(OUT_FILE) // 1024} kB)")


if __name__ == "__main__":
    main()
