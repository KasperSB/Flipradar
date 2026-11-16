"""Flipradar: dataindsamling for villaer og rækkehuse i resten af Sjælland.

Kør med regionens navn, fx:  python scripts/update_sj.py omegn
Genbruger hele beregningen fra update.py, men med regionens postnumre, kun villaer
og rækkehuse, handler fra de seneste 12 måneder og nære handler inden for 500 m (1.000 m hvis der er under 5).
Hver region gemmes i sin egen datafil, så siden kun henter den region, man kigger på.
"""
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402


def chunks(lo, hi, step=100):
    """Del et postnummerinterval op i bidder, så hver søgning hos Boliga holder sig lille."""
    out, a = [], lo
    while a <= hi:
        b = min(hi, (a // step) * step + step - 1)
        out.append((a, b))
        a = b + 1
    return out


REGIONS = {
    "omegn": {"name": "Københavns omegn", "file": "omegn",
              "ranges": [(2600, 2699), (2730, 2799), (2800, 2959)]},
    "nsj": {"name": "Nordsjælland", "file": "nordsjaelland_huse",
            "ranges": [(2960, 2999), (3000, 3699)]},
    "vest": {"name": "Midt- og Vestsjælland", "file": "vest",
             "ranges": [(4000, 4159), (4173, 4599)]},
    "syd": {"name": "Sydsjælland", "file": "syd",
            "ranges": [(4160, 4172), (4600, 4799)]},
}

DAYS = 365        # handler fra de seneste 12 måneder
RADII = [500, 1000]  # nære handler: først 500 m, og 1.000 m kun hvis der er under 5 handler
MAX_PRICE = 6_000_000

key = sys.argv[1] if len(sys.argv) > 1 else ""
if key not in REGIONS:
    sys.exit("Angiv en region: " + ", ".join(REGIONS))
R = REGIONS[key]
RANGES = [c for lo, hi in R["ranges"] for c in chunks(lo, hi)]
in_region = lambda z: any(lo <= z <= hi for lo, hi in R["ranges"])  # noqa: E731

U.OUT_FILE = os.path.join(U.ROOT, "data", R["file"] + ".json")
U.SALES_CACHE = os.path.join(U.ROOT, "data", "sales_" + R["file"] + ".json")
U.MAX_PRICE = MAX_PRICE
U.SALES_DAYS = DAYS
U.FALLBACK_DAYS = DAYS
U.NAER_RADII = RADII
U.NAER_RADIUS = RADII[-1]
U.STEPS = [(DAYS, 1000), (DAYS, 2000), (DAYS, 4000), (DAYS, 8000)]
U.ZIP_RANGES = RANGES
U.LISTING_TYPES = "villa,terraced house"
U.TYPE_MAP = {"villa": "Villa", "terraced house": "Rækkehus"}
U.GROUP = {"Villa": "villa", "Rækkehus": "raekke"}
U.BOLIGA_GROUP = {1: "villa", 2: "raekke"}
U.ZONE_GROUP = "villa"
U.SPECIAL = re.compile(
    r"udlejet|\blejer(?:en|ne)?\b|lejekontrakt|investeringsbolig|\bandel|haveforening|kolonihave|"
    r"\bhf\.|lejet grund|ikke godkendt til (?:hel[åa]rs)?beboelse|erhvervsejendom|byggegrund|"
    r"grund til salg|nedrivningsklar|tvangsauktion|auktion", re.I)

# Bynavn pr. postnummer, så man kan vælge byer i områdevælgeren
ZIPNAME = {}


def district(zip_code):
    try:
        z = int(zip_code)
    except (TypeError, ValueError):
        return None
    if not in_region(z):
        return None
    return ZIPNAME.get(z) or str(z)


def nearest_zone(d, _lat, _lon):
    return d  # ét område pr. by


_parse_sale, _parse_case = U.parse_sale, U.parse_case


def parse_sale(r):
    try:
        z = int(r.get("zipCode"))
        if in_region(z) and r.get("city"):
            ZIPNAME.setdefault(z, r["city"])
    except (TypeError, ValueError):
        pass
    return _parse_sale(r)


def parse_case(c):
    a = c.get("address") or {}
    try:
        z = int(a.get("zipCode") or (a.get("zip") or {}).get("zipCode"))
        name = (a.get("zip") or {}).get("name") or a.get("cityName")
        if in_region(z) and name:
            ZIPNAME[z] = name
    except (TypeError, ValueError):
        pass
    return _parse_case(c)


_fetch_listings = U.fetch_listings


def fetch_listings(sales):
    # Spørg Boligsiden på de postnumre, der findes i regionen (kendt fra Boligas handler)
    U.SINGLE_ZIPS = sorted({int(s["postnr"]) for s in sales if s.get("postnr")})
    return _fetch_listings(sales)


_zone_stats = U.zone_stats


def zone_stats(sales):
    # Ét område pr. by med midtpunkt i byens handler. Alle byer rangeres samlet.
    pts = {}
    for s in sales:
        pts.setdefault(s["zone"], []).append((s["lat"], s["lng"]))
    U.ZONES = [(z, R["name"], z, statistics.mean(p[0] for p in v), statistics.mean(p[1] for p in v))
               for z, v in sorted(pts.items()) if z]
    return _zone_stats(sales)


U.district = district
U.nearest_zone = nearest_zone
U.parse_sale = parse_sale
U.parse_case = parse_case
U.fetch_listings = fetch_listings
U.zone_stats = zone_stats

if __name__ == "__main__":
    U.log(f"=== {R['name']}: villaer og rækkehuse, postnumre "
          + ", ".join(f"{lo}-{hi}" for lo, hi in R["ranges"]) + " ===")
    U.main()
