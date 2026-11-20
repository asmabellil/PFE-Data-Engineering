# JobCompass, la boussole du marché de l'emploi

Plateforme Big Data de collecte et d'analyse des offres d'emploi.
PFE Master 2 Data Engineering : Asma BELLIL · Ghaylene DRIDI · Mohamed Yacine BRAHMIA (2026-2027).

Collecte automatique d'offres d'emploi (API et sitemap), ingestion **Kafka**, data lake **MinIO**,
traitement **Spark** (nettoyage, NLP, qualité des données, dédoublonnage), entrepôt **MongoDB**,
orchestration **Airflow**, application **React + FastAPI** sécurisée et servie en **HTTPS**, et **IA**
(scikit-learn, Transformers, PyTorch). Le tout tourne dans **Docker**.

```
Sources ─► Collecteurs Python ─► Kafka ─► MinIO (raw) ─► Spark ─► porte de qualité ─► MongoDB ─► FastAPI ─► Caddy (HTTPS) ─► React
                                                           └─► MinIO (processed, quarantine, gold) et exports CSV
                                  Airflow orchestre l'ensemble (toutes les 6 h)
```

## Nouveautés de la version 2

| Domaine | Ce qui change |
|---|---|
| **Sources** | Nouveaux collecteurs **France Travail** (OAuth2, découpage automatique au-delà de 3 150 résultats par région, département puis période, retrait des coordonnées des recruteurs) et **Adzuna** (clé jamais écrite dans les logs). Périmètre réglable dans `.env` (codes ROME, mots-clés, plafond de pages, collecte incrémentale). |
| **Périmètre Tech/Data** | Chaque offre porte une étiquette `tech_scope`. L'application affiche par défaut les seuls métiers Tech/Data (interrupteur dans la barre de filtres). Le sitemap Welcome to the Jungle est filtré sur les intitulés Tech/Data. Rien n'est supprimé. |
| **Qualité des données** | Porte de qualité au niveau du lot, entre Spark et MongoDB : chargement bloqué au-delà de 20 % d'offres en quarantaine, alertes de chute de volume et de fraîcheur par source. Nouveau contrôle des salaires inexploitables. |
| **Dédoublonnage** | Dédoublonnage par similarité (MinHash LSH, Spark MLlib) des offres republiées d'une source à l'autre, en plus du dédoublonnage exact. Règles validées sur les données réelles. |
| **Analyses** | Médiane des salaires par devise (devise d'origine et équivalent en euros) et par pays, avec le nombre d'offres. Évolution des offres par source. |
| **Sécurité** | HTTPS avec Caddy (redirection, HSTS). Jeton d'accès de 15 min, refresh token en cookie httpOnly, Secure, SameSite=Strict, avec rotation et détection de vol. Verrouillage après 5 échecs. Dépendances vulnérables corrigées (PyJWT, PyMongo, React Router, Vite). |
| **CI** | GitHub Actions : tests du pipeline et de l'API, build du front, scans de sécurité (gitleaks, Bandit, pip-audit, npm audit, Trivy). Dependabot chaque semaine. |
| **Interface** | Nouveau nom JobCompass, menu latéral repliable, thème clair et sombre, code couleur des graphiques avec légende, états de chargement. |

## Démarrage rapide

Pré-requis : Docker Desktop (8 Go de RAM alloués, environ 25 Go de disque libre).

```powershell
cp .env.example .env        # puis remplacer chaque "change-me" par un secret aléatoire
docker compose up -d --build
```

| Interface | Adresse |
|---|---|
| Application | **https://localhost** (compte : `ADMIN_EMAIL` / `ADMIN_PASSWORD` du `.env`) |
| API (Swagger) | http://localhost:8000/docs |
| Airflow | http://localhost:8080 |
| MinIO | http://localhost:9001 |

Le certificat HTTPS est signé par l'autorité locale de Caddy. Le navigateur affiche donc un avertissement au premier accès.
Pour lancer le pipeline : Airflow, DAG `jobinsight_pipeline`, bouton « Trigger ».

### Sources avec clé (optionnelles)

Sans clé, ces deux sources sont simplement ignorées. Avec une clé, il suffit de la mettre dans `.env` puis de relancer Airflow (`docker compose up -d airflow`).

| Source | Inscription | Variables |
|---|---|---|
| France Travail | https://francetravail.io (application avec l'API « Offres d'emploi v2 ») | `FRANCE_TRAVAIL_CLIENT_ID`, `FRANCE_TRAVAIL_CLIENT_SECRET` |
| Adzuna | https://developer.adzuna.com | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` |

## Structure

```
├── docker-compose.yml      toute la plateforme (dont Caddy pour le HTTPS)
├── docker/caddy/           configuration du reverse proxy HTTPS
├── pipeline/jobinsight/    collecte, ingestion, lake, Spark, qualité, dédoublonnage, MongoDB, KPIs, ML
├── airflow/                image Airflow et DAGs
├── backend/                API FastAPI (sessions, sécurité, analyses, IA)
├── frontend/               application React
├── docs/                   documentation technique par composant (00 à 13)
├── .github/                CI et Dependabot
└── exports/ models/ data/  générés (non versionnés)
```

## Documentation

| # | Sujet |
|---|---|
| [00](docs/00-architecture.md) | Architecture, modèle de données, choix, perspectives |
| [01](docs/01-collecte-api-scraping.md) | Collecte : API et sitemap |
| [02](docs/02-ingestion-kafka.md) | Ingestion : Kafka |
| [03](docs/03-orchestration-airflow.md) | Orchestration : Airflow |
| [04](docs/04-data-lake-minio.md) | Data lake : MinIO |
| [05](docs/05-traitement-spark.md) | Traitement : Spark |
| [06](docs/06-data-quality-deduplication.md) | Qualité des données et dédoublonnage |
| [07](docs/07-stockage-mongodb.md) | Stockage : MongoDB |
| [08](docs/08-ia-ml-deep-learning.md) | IA : ML et Deep Learning |
| [09](docs/09-backend-fastapi.md) | Backend : FastAPI |
| [10](docs/10-frontend-react.md) | Frontend : React |
| [11](docs/11-power-bi.md) | Exports CSV et guide Power BI |
| [12](docs/12-securite.md) | Sécurité (dont HTTPS) |
| [13](docs/13-docker-devops.md) | Docker et DevOps |

## Tests

```bash
cd pipeline && pip install -e ".[dev,ml]" && pytest -q        # 101 tests (le test Spark demande pyspark)
cd backend  && pip install -r requirements.txt -r requirements-dev.txt -e ../pipeline && pytest -q   # 19 tests
cd frontend && npm ci && npm run build
```

La CI GitHub Actions lance ces tests et les scans de sécurité à chaque push et à chaque Pull Request.

## Sources de données et attribution

Offres issues de [Welcome to the Jungle](https://www.welcometothejungle.com) (sitemap public, sans lecture
des pages qui refusent les robots), [Arbeitnow](https://www.arbeitnow.com), [Jobicy](https://jobicy.com),
[Remotive](https://remotive.com), [python.org/jobs](https://www.python.org/jobs/) et, si les clés sont configurées,
[France Travail](https://francetravail.io) et [Adzuna](https://www.adzuna.fr).
Chaque offre affichée cite sa source et renvoie vers l'annonce originale.
