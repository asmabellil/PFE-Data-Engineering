# 04 – Data Lake : MinIO (compatible S3)

**Outils** : MinIO (stockage objet S3), `boto3`, format **JSONL** (raw) et **Parquet** (processed / gold)
**Code** : `pipeline/jobinsight/lake.py` · **Console** : http://localhost:9001

## Organisation en zones (architecture « médaillon »)

```
datalake/                                   (bucket versionné)
├── raw/<source>/<YYYY-MM-DD>/batch_<run>.jsonl     BRONZE : données brutes, immuables
├── processed/jobs/<YYYY-MM-DD>/<run>/*.parquet     SILVER : nettoyées, enrichies, dédupliquées
├── quarantine/<YYYY-MM-DD>/<run>/*.parquet         données non conformes (Data Quality)
├── gold/<run>/<kpi>/*.parquet                      GOLD : agrégats analytiques (KPIs)
└── reports/quality/<run>.json                      rapports de qualité
```
Correspond exactement au Livrable 1 §10.3 (`data/raw/source_1/2026-09-01/`).

## Pourquoi conserver le brut ?
- **Reproductibilité** : si une règle de nettoyage change, on retraite l'historique sans re-collecter.
- **Audit** : on peut toujours prouver ce que la source a renvoyé.
- **Historisation** : un fichier par lot et par jour.

## Formats
| Zone | Format | Raison |
|---|---|---|
| raw | JSON Lines | fidèle à la réponse de l'API, ajout ligne par ligne |
| processed / gold | **Parquet** | colonnaire, compressé, typé, lu nativement par Spark / pandas / Power BI |

## Sécurité
- Accès par clés (`MINIO_ROOT_USER/PASSWORD` dans `.env`), ports publiés sur `127.0.0.1` uniquement.
- **Versioning** activé à la création du bucket (protection contre l'écrasement / suppression).
- Évolution : utilisateur MinIO dédié au pipeline avec une policy limitée au bucket `datalake`.

## Exemple d'utilisation
```python
from jobinsight.lake import DataLake
lake = DataLake()
lake.ensure_bucket()
lake.list_keys("raw/jobicy/")
```
