# 13 – Conteneurisation et DevOps : Docker

**Outils** : Docker, Docker Compose v2, Git (stratégie de branches du Livrable 1 §19.2), pytest

## Services (`docker-compose.yml`)

| Service | Image | Port (127.0.0.1) | Rôle |
|---|---|---|---|
| `postgres` | postgres:16-alpine | – | métadonnées Airflow |
| `airflow` | **custom** (airflow 2.10.4 + Java 17 + PySpark + jobinsight) | 8080 | orchestration + Spark local |
| `kafka` | apache/kafka:3.9.0 (KRaft) | 29092 | ingestion |
| `kafka-ui` | provectuslabs/kafka-ui:v0.7.2 (profil `admin`) | 8081 | observation des topics |
| `minio` | bitnamilegacy/minio (MinIO 2025-04-22) | 9000 / 9001 | Data Lake |
| `mongo` | mongo:7.0 | 27018 (→ 27017 interne) | entrepôt / serving |
| `backend` | **custom** (python 3.11 + FastAPI + PyTorch CPU) | 8000 | API + IA |
| `frontend` | **custom** (build node 20 → nginx 1.27) | 3000 | application web |

Volumes nommés pour la persistance (`mongo_data`, `minio_data`, `kafka_data`, `postgres_data`,
`hf_cache` pour le modèle Transformer) ; dossiers montés : `pipeline/` (code), `airflow/dags/`,
`exports/` (Power BI), `models/` (modèles partagés Airflow ↔ API).

**Healthchecks** sur Postgres, Kafka, MinIO, MongoDB et l'API ; Airflow attend que ses
dépendances soient *healthy* (`depends_on: condition: service_healthy`). Mémoire maîtrisée
(Kafka 512 Mo, cache MongoDB 0,5 Go, driver Spark 1 Go) → la plateforme tient sur 8 Go.

## Commandes
```bash
docker compose up -d --build            # démarrer / reconstruire
docker compose ps                        # état
docker compose logs -f airflow backend   # logs
docker compose exec airflow python -m jobinsight.cli all --run-id demo   # pipeline à la main
docker compose down                      # arrêter (données conservées)
docker compose down -v                   # tout supprimer (volumes inclus)
```

## Images multi-étapes / bonnes pratiques
- Front : build Node puis copie du `dist/` dans nginx (image finale légère, sans Node).
- API : PyTorch **CPU** (≈ 5× plus léger que CUDA), utilisateur non-root, `PIP_NO_CACHE_DIR`.
- Airflow : installation *editable* du code → itérations sans rebuild.

## Tests
| Suite | Commande | Résultat |
|---|---|---|
| Pipeline (38 tests) | `cd pipeline && pytest -q` | ✅ |
| API (8 tests) | `cd backend && pytest -q` | ✅ |
| Build front | `cd frontend && npm run build` | ✅ |

## Git (Livrable 1 §19.2)
`main` (stable) ← `develop` ← `feature/data-collection`, `feature/data-ingestion`,
`feature/data-processing`, `feature/analytics`, `feature/dashboard` ; fusion par Merge Request revue.
CI/CD GitLab possible (perspective) : jobs `test` (pytest), `build` (docker build), `lint`.
