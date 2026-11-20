"""Profilage de la zone Raw : taux de remplissage et types des champs de chaque source.

Sert à calibrer les contrats de données (jobinsight/ingestion/contracts.py) sur les vraies données.
Usage (le dossier scripts/ n'est pas monté dans le conteneur Airflow, on le copie) :
    docker compose cp scripts/profile_raw_fields.py airflow:/tmp/
    docker compose exec airflow python /tmp/profile_raw_fields.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from jobinsight.lake import DataLake

lake = DataLake()
keys = lake.list_keys("raw/")
latest: dict[str, str] = {}
for key in sorted(keys):  # raw/<source>/<date>/batch_<run>.jsonl : le tri garde le plus récent
    latest[key.split("/")[1]] = key

for source, key in sorted(latest.items()):
    # split("\n") et non splitlines() : les descriptions contiennent des U+2028 que splitlines() coupe
    lines = [l for l in lake.get_bytes(key).decode("utf-8").split("\n") if l.strip()]
    filled, types = Counter(), defaultdict(Counter)
    for line in lines:
        payload = json.loads(line)["payload"]
        for field, value in payload.items():
            types[field][type(value).__name__] += 1
            if value not in (None, "", [], {}):
                filled[field] += 1
    print(f"\n== {source} ({len(lines)} offres, {key})")
    for field in sorted(types, key=lambda f: -filled[f]):
        pct = 100 * filled[field] / len(lines)
        print(f"  {field:28} {pct:5.1f} %  {dict(types[field])}")
