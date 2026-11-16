# 07 – Stockage analytique : MongoDB

**Outils** : MongoDB 7.0, `pymongo` (bulk upserts, agrégations), MongoDB Compass (exploration)
**Code** : `pipeline/jobinsight/warehouse/mongo_loader.py`, `docker/mongo/init-mongo.js`

## Rôle
Couche **Processed / Warehouse** et base de l'application web : dernière version consolidée de
chaque offre + collections techniques (monitoring, IA, sécurité).

| Collection | Contenu |
|---|---|
| `jobs` | offres consolidées (modèle de données, doc 00) |
| `quality_reports`, `pipeline_runs` | monitoring du pipeline |
| `kpi_snapshots` | historique des KPIs globaux à chaque run |
| `ml_runs`, `ml_clusters`, `job_embeddings` | IA |
| `users`, `audit_logs` | sécurité |

## Chargement idempotent
```python
UpdateOne({"dedup_key": key}, {
    "$set": doc,                              # dernière version
    "$setOnInsert": {"first_seen_at": now},   # date de première détection
    "$max": {"last_seen_at": now},
    "$inc": {"seen_count": 1},
    "$addToSet": {"sources": {"$each": sources}},
}, upsert=True)
```
Envoyé par paquets de 1 000 (`bulk_write`, `ordered=False`).

## Index
| Index | Usage |
|---|---|
| `dedup_key` **unique** | dédup inter-lots |
| `publication_date` (desc) | tri, filtres de période, timeline |
| `country`, `contract_type`, `experience_level`, `industry`, `sources`, `technologies`, `skills`, `remote`, `cluster_id` | filtres du dashboard |
| index **texte** pondéré (titre ×10, entreprise ×5, description ×1) | recherche plein texte |

## KPIs par agrégation (API)
Exemple « Top technologies » :
```js
[{ $match: filtres }, { $unwind: "$technologies" },
 { $group: { _id: "$technologies", jobs: { $sum: 1 } } }, { $sort: { jobs: -1 } }, { $limit: 15 }]
```
La vue d'ensemble utilise `$facet` (8 indicateurs en une seule requête), la distribution des
salaires `$bucket`.

## Sécurité
- `--auth` activé ; **un utilisateur par usage** (`init-mongo.js`) : `jobinsight_pipeline`
  (readWrite), `jobinsight_api` (readWrite), `jobinsight_bi` (**lecture seule**, pour Compass /
  Power BI). Le compte root n'est utilisé par aucun service.
- Port publié uniquement sur `127.0.0.1`.

## Explorer avec Compass
`mongodb://jobinsight_bi:<MONGO_BI_PASSWORD>@localhost:27018/jobinsight?authSource=jobinsight`
