# JobInsight – Plateforme Big Data de collecte et d'analyse des offres d'emploi

PFE Master 2 Data Engineering – Asma BELLIL · Ghaylene DRIDI · Mohamed Yacine BRAHMIA (2026-2027)

Collecte automatique d'offres d'emploi (API + web scraping), ingestion **Kafka**, Data Lake
**MinIO**, traitement **Spark** (nettoyage, NLP, Data Quality, déduplication), entrepôt
**MongoDB**, orchestration **Airflow**, application **React + FastAPI** sécurisée, reporting
**Power BI** et **IA** (scikit-learn, Transformers, PyTorch) – le tout dans **Docker**.

```
Sources ─► Collecteurs Python ─► Kafka ─► MinIO (raw) ─► Spark ─► MinIO (processed/gold) ─► MongoDB ─► FastAPI ─► React
                                                                       └─► exports CSV ─► Power BI
                                  Airflow orchestre l'ensemble (toutes les 6 h)
```

## Démarrage rapide
Pré-requis : Docker Desktop (≥ 8 Go de RAM alloués, ~25 Go de disque libre).
```powershell
cp .env.example .env        # puis remplacer chaque "change-me" (déjà fait sur le poste de dev)
docker compose up -d --build
```
| Interface | URL |
|---|---|
| Application | http://localhost:3000 (compte : `ADMIN_EMAIL` / `ADMIN_PASSWORD` du `.env`) |
| API (Swagger) | http://localhost:8000/docs |
| Airflow | http://localhost:8080 |
| MinIO | http://localhost:9001 |

Puis Airflow → `jobinsight_pipeline` → ▶ Trigger ; après quelques runs : `jobinsight_ml` → ▶ Trigger.

## Structure
```
├── ROADMAP.md              plan, planning, répartition, livrables
├── docker-compose.yml      toute la plateforme
├── pipeline/jobinsight/    collecte, ingestion, lake, traitement Spark, qualité, MongoDB, KPIs, ML
├── airflow/                image Airflow + DAGs
├── backend/                API FastAPI (sécurité, analytics, IA Deep Learning)
├── frontend/               application React
├── powerbi/                guide Power BI (modèle, DAX, pages)
├── docs/                   documentation technique par composant (00 → 13)
└── exports/ models/ data/  générés (non versionnés)
```

## Documentation
| # | Sujet |
|---|---|
| [00](docs/00-architecture.md) | Architecture, modèle de données, choix, perspectives |
| [01](docs/01-collecte-api-scraping.md) | Collecte : API & web scraping |
| [02](docs/02-ingestion-kafka.md) | Ingestion : Kafka |
| [03](docs/03-orchestration-airflow.md) | Orchestration : Airflow |
| [04](docs/04-data-lake-minio.md) | Data Lake : MinIO |
| [05](docs/05-traitement-spark.md) | Traitement : Spark |
| [06](docs/06-data-quality-deduplication.md) | Data Quality & déduplication |
| [07](docs/07-stockage-mongodb.md) | Stockage : MongoDB |
| [08](docs/08-ia-ml-deep-learning.md) | IA : ML & Deep Learning |
| [09](docs/09-backend-fastapi.md) | Backend : FastAPI |
| [10](docs/10-frontend-react.md) | Frontend : React |
| [11](docs/11-power-bi.md) | Power BI |
| [12](docs/12-securite.md) | Sécurité |
| [13](docs/13-docker-devops.md) | Docker & DevOps |

## Tests
```bash
cd pipeline && pip install -e ".[dev,ml]" && pytest -q          # 38 tests
cd backend  && pip install -r requirements.txt -r requirements-dev.txt -e ../pipeline && pytest -q   # 8 tests
cd frontend && npm install && npm run build
```

## Sources de données et attribution
Offres issues d'[Arbeitnow](https://www.arbeitnow.com), [Jobicy](https://jobicy.com),
[Remotive](https://remotive.com), [python.org/jobs](https://www.python.org/jobs/) et, si configurées,
Adzuna et France Travail. Chaque offre affichée cite sa source et renvoie vers l'annonce originale.
