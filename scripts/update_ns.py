"""Flipradar: dataindsamling for sommerhuse i Nordsjælland (Tisvildeleje til Helsingør).

Genbruger hele beregningen fra update.py, men med andre postnumre, kun sommerhuse
og handler fra de seneste 12 måneder. Resultatet gemmes i data/nordsjaelland.json.
"""
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402

TOWNS = {3220: "Tisvildeleje", 3210: "Vejby", 3230: "Græsted", 3250: "Gilleleje",
         3120: "Dronningmølle", 3100: "Hornbæk", 3140: "Ålsgårde", 3150: "Hellebæk",
         3000: "Helsingør"}

# Områder langs kysten. Alle rangeres samlet fra 1 til 10 ud fra sommerhuspriserne.
ZONES = [
    ("ns1", "Nordkysten", "Tisvildeleje", 56.0520, 12.0820),
    ("ns2", "Nordkysten", "Vejby Strand", 56.0830, 12.1300),
    ("ns3", "Nordkysten", "Rågeleje", 56.0970, 12.1550),
    ("ns4", "Nordkysten", "Udsholt og Pårup", 56.1080, 12.2000),
    ("ns5", "Nordkysten", "Smidstrup Strand", 56.1170, 12.2500),
    ("ns6", "Nordkysten", "Gilleleje", 56.1220, 12.3050),
    ("ns7", "Nordkysten", "Dronningmølle", 56.1000, 12.3980),
    ("ns8", "Nordkysten", "Hornbæk", 56.0910, 12.4580),
    ("ns9", "Nordkysten", "Ålsgårde", 56.0750, 12.5350),
    ("ns10", "Nordkysten", "Hellebæk", 56.0680, 12.5550),
    ("ns11", "Nordkysten", "Helsingør", 56.0360, 12.6040),
]

DAYS = 365

U.OUT_FILE = os.path.join(U.ROOT, "data", "nordsjaelland.json")
U.SALES_CACHE = os.path.join(U.ROOT, "data", "sales_ns.json")
U.SALES_DAYS = DAYS
U.FALLBACK_DAYS = DAYS
U.STEPS = [(DAYS, 1000), (DAYS, 2000), (DAYS, 4000), (DAYS, 8000)]
U.ZIP_RANGES = [(z, z) for z in sorted(TOWNS)]
U.SINGLE_ZIPS = sorted(TOWNS)
U.LISTING_TYPES = "holiday house"
U.TYPE_MAP = {"holiday house": "Sommerhus"}
U.GROUP = {"Sommerhus": "hus"}
U.BOLIGA_GROUP = {4: "hus"}  # 4 = fritidshus hos Boliga
U.ZONES = ZONES
U.ZONE_GROUP = "hus"
# Samme liste over særlige vilkår, men uden ordene sommerhus og fritidsbolig
U.SPECIAL = re.compile(
    r"udlejet|\blejer(?:en|ne)?\b|lejekontrakt|investeringsbolig|\bandel|haveforening|kolonihave|"
    r"\bhf\.|lejet grund|erhvervsejendom|byggegrund|grund til salg|tvangsauktion|auktion", re.I)


def district(zip_code):
    try:
        return TOWNS.get(int(zip_code))
    except (TypeError, ValueError):
        return None


def nearest_zone(_d, lat, lon):
    return min(ZONES, key=lambda z: U.dist_m(lat, lon, z[3], z[4]))[0]


U.district = district
U.nearest_zone = nearest_zone

# Tæl boligtyper i Boligas data, så vi kan se, om sommerhuse genkendes korrekt
seen_types = collections.Counter()
_parse_sale = U.parse_sale


def parse_sale(r):
    seen_types[r.get("propertyType")] += 1
    return _parse_sale(r)


U.parse_sale = parse_sale

if __name__ == "__main__":
    U.log("=== Nordsjælland: sommerhuse fra Tisvildeleje til Helsingør ===")
    try:
        U.main()
    finally:
        U.log("Boligtyper i Boligas handler (4 = fritidshus): "
              + ", ".join(f"{k}: {v}" for k, v in sorted(seen_types.items(), key=lambda x: str(x[0]))))
