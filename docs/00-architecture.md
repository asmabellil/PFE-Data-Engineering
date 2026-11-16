# 00 – Architecture globale et choix technologiques

## Vue d'ensemble

```
                         ┌───────────────── Apache Airflow (orchestration, monitoring) ─────────────────┐
                         │                                                                                │
 Sources ──► Collecteurs ──► Apache Kafka ──► MinIO Data Lake ──► Apache Spark ──► MongoDB ──► FastAPI ──► React
 (API +      Python          topic jobs.raw    raw/                ETL + DQ +        entrepôt     JWT/RBAC     dashboard
 scraping)   requests/bs4                       processed/          dédup + KPIs                  IA (ML/DL)
                                                quarantine/  ──────────────────► gold/ + exports CSV ──► Power BI
                                                gold/ reports/
```

| Couche du Livrable 1 | Technologie | Dossier |
|---|---|---|
| Data Collection – API / Scraping | Python, `requests`, `BeautifulSoup`, `urllib.robotparser` | `pipeline/jobinsight/collectors/` |
| Data Ingestion – Batch / Streaming | Apache Kafka 3.9 (KRaft), `confluent-kafka` | `pipeline/jobinsight/ingestion/` |
| Raw Data Storage – Data Lake | MinIO (S3), `boto3` | `pipeline/jobinsight/lake.py` |
| Data Processing – Cleaning / ETL / Dédup | Apache Spark 3.5 (PySpark) | `pipeline/jobinsight/processing/` |
| Processed Data – Data Warehouse | MongoDB 7 (+ Parquet en zone gold) | `pipeline/jobinsight/warehouse/` |
| Analytics – KPIs / Agrégations | Spark SQL, agrégations MongoDB | `pipeline/jobinsight/analytics/`, `backend/app/routers/analytics.py` |
| Dashboard – Visualisation | React 18 + Recharts, Power BI | `frontend/`, `powerbi/` |
| IA | scikit-learn, Sentence-Transformers, PyTorch | `pipeline/jobinsight/ml/`, `backend/app/ai/` |
| Orchestration | Apache Airflow 2.10 | `airflow/dags/` |
| Conteneurisation | Docker, Docker Compose | `docker-compose.yml`, `*/Dockerfile` |

## Cycle de vie de la donnée (Livrable 1 §6.2)

`Sources → Collecte → Ingestion (Kafka) → Data Lake raw → Traitement (Spark) → Data Quality
(quarantaine) → processed → Warehouse (MongoDB) → Analytics (gold, API) → Dashboard (React, Power BI)`

## Modèle de données (document `jobs` dans MongoDB)

| Champ | Description |
|---|---|
| `dedup_key` (unique) | SHA-1(entreprise + titre + ville normalisés) – identité inter-sources |
| `job_id` | SHA-1(source + id source) |
| `title`, `company`, `description` | nettoyés (HTML retiré, PII masquées) |
| `location`, `city`, `country`, `region`, `remote` | normalisation géographique |
| `contract_type` | full_time, part_time, contract, freelance, internship, apprenticeship, temporary |
| `experience_level`, `years_experience` | intern, junior, mid, senior, lead + années extraites |
| `salary_min/max`, `currency`, `salary_period`, `salary_annual_min_eur/max_eur` | salaire brut + annualisé en EUR |
| `skills`, `technologies`, `tags` | extraits par NLP |
| `industry`, `industry_source`, `industry_confidence` | secteur source ou prédit par ML |
| `publication_date`, `url`, `source`, `sources[]` | traçabilité |
| `first_seen_at`, `last_seen_at`, `seen_count` | historisation |
| `completeness`, `dq_issues[]` | qualité |
| `cluster_id` | famille de métiers (K-Means) |

Autres collections : `pipeline_runs`, `quality_reports`, `kpi_snapshots`, `ml_runs`, `ml_clusters`,
`job_embeddings`, `users`, `audit_logs`.

## Pourquoi ces choix ?

- **Kafka** découple la collecte du stockage : un collecteur ne dépend pas de la disponibilité du
  Data Lake, les messages sont conservés 7 jours (rejeu possible) et le passage au streaming ne
  demande aucun changement côté collecteurs.
- **MinIO** fournit un stockage objet compatible S3 en local : même code que sur AWS S3.
  Le bucket est **versionné** (historisation, protection contre l'écrasement).
- **Spark** : traitements distribués (map, window functions, agrégations SQL) – le même job tourne
  en local (`local[*]`) ou sur un cluster.
- **MongoDB** : schéma flexible (offres hétérogènes, tableaux de compétences), index plein texte,
  agrégations puissantes pour les KPIs, requis par la stack web demandée.
- **Airflow** : planification, dépendances, retries, logs, interface de supervision.
- **FastAPI** : performance, validation automatique (Pydantic), documentation OpenAPI générée.
- **React** : SPA réactive ; **Power BI** : outil standard des analystes.

## Perspectives (pour la conclusion du rapport)
- Streaming temps réel (Kafka consumer continu / Spark Structured Streaming).
- Cluster Spark (ou Databricks) et Data Warehouse cloud (BigQuery / Snowflake) si le volume augmente.
- Lecture directe S3A depuis Spark, format Delta Lake / Iceberg (ACID, time travel).
- Géocodage (Nominatim) pour les petites villes ; détection de langue.
- CI/CD GitLab (tests + build des images), monitoring Prometheus / Grafana, HTTPS (Traefik).
- Prédiction de tendances (séries temporelles) une fois plusieurs mois d'historique accumulés.
