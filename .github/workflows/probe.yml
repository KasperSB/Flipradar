name: Prøvekørsel af datakilder

on:
  workflow_dispatch:

permissions:
  contents: write

jobs:
  probe:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Spørg Boligsiden og Boliga
        run: python scripts/probe.py
      - name: Gem resultatet i projektet
        run: |
          git config user.name "flipradar-bot"
          git config user.email "flipradar-bot@users.noreply.github.com"
          git add data/probe
          git commit -m "Prøvekørsel $(date -u +%Y-%m-%d_%H%M)" || echo "Intet nyt at gemme"
          git push
