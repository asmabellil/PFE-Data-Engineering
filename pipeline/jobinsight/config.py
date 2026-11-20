"""Configuration centralisée du pipeline JobCompass.

Toutes les valeurs proviennent des variables d'environnement (fichier .env chargé par
docker compose). Aucun secret n'est écrit en dur dans le code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_list(name: str, default: str) -> list[str]:
    return [v.strip() for v in (_env(name, default) or "").split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    # --- Ingestion (Kafka) ---
    ingestion_mode: str          # "kafka" (production) ou "file" (dev / tests sans Kafka)
    kafka_bootstrap: str
    kafka_topic_raw: str
    kafka_group_lake: str

    # --- Data Lake (MinIO / S3) ---
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    lake_bucket: str

    # --- Data Warehouse / serving (MongoDB) ---
    mongo_uri: str
    mongo_db: str

    # --- Dossiers locaux ---
    local_data_dir: str
    exports_dir: str
    models_dir: str

    # --- Collecte ---
    user_agent: str
    request_delay_s: float
    arbeitnow_max_pages: int
    jobicy_geos: list[str]
    pythonorg_max_pages: int
    pythonorg_max_details: int
    wttj_max_jobs: int
    wttj_days: int
    wttj_langs: list[str]
    adzuna_app_id: str | None
    adzuna_app_key: str | None
    adzuna_countries: list[str]
    adzuna_keywords: list[str]
    ft_client_id: str | None
    ft_client_secret: str | None
    ft_keywords: list[str]
    # périmètre et volume des sources françaises (valeurs par défaut = France, métiers Tech/Data)
    ft_rome_codes: list[str] = field(default_factory=list)
    ft_since_days: int = 0       # 0 = toutes les offres actives ; N = créées dans les N derniers jours
    ft_max_pages: int = 0        # 0 = pas de plafond ; N = au plus N pages de 150 offres par run
    adzuna_max_pages: int = 20   # pages de 50 offres par recherche (quota gratuit limité)
    adzuna_max_days_old: int = 0  # 0 = pas de filtre de date
    wttj_tech_only: bool = True  # ne garder que les intitulés Tech/Data du sitemap WTTJ (tous métiers sinon)
    kafka_topic_dlq: str = "jobs.dlq"  # file de rejet : offres qui violent le contrat de données


def get_settings() -> Settings:
    return Settings(
        ingestion_mode=_env("INGESTION_MODE", "kafka"),
        kafka_bootstrap=_env("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092"),
        kafka_topic_raw=_env("KAFKA_TOPIC_RAW", "jobs.raw"),
        kafka_group_lake=_env("KAFKA_GROUP_LAKE", "lake-writer"),
        kafka_topic_dlq=_env("KAFKA_TOPIC_DLQ", "jobs.dlq"),
        minio_endpoint=_env("MINIO_ENDPOINT", "http://localhost:9000"),
        minio_access_key=_env("MINIO_ROOT_USER", "minioadmin"),
        minio_secret_key=_env("MINIO_ROOT_PASSWORD", "minioadmin"),
        lake_bucket=_env("LAKE_BUCKET", "datalake"),
        mongo_uri=_env("MONGO_URI", "mongodb://localhost:27017"),
        mongo_db=_env("MONGO_DB", "jobinsight"),
        local_data_dir=_env("LOCAL_DATA_DIR", "./data"),
        exports_dir=_env("EXPORTS_DIR", "./exports"),
        models_dir=_env("MODELS_DIR", "./models"),
        user_agent=_env(
            "HTTP_USER_AGENT",
            "JobCompass-PFE/1.0 (projet etudiant Master Data Engineering)",
        ),
        request_delay_s=float(_env("REQUEST_DELAY_S", "1.0")),
        arbeitnow_max_pages=_env_int("ARBEITNOW_MAX_PAGES", 3),
        jobicy_geos=_env_list("JOBICY_GEOS", "all,europe,france,usa,uk,canada,germany"),
        pythonorg_max_pages=_env_int("PYTHONORG_MAX_PAGES", 3),
        pythonorg_max_details=_env_int("PYTHONORG_MAX_DETAILS", 40),
        wttj_max_jobs=_env_int("WTTJ_MAX_JOBS", 5000),
        wttj_days=_env_int("WTTJ_DAYS", 7),
        wttj_langs=_env_list("WTTJ_LANGS", "fr"),
        wttj_tech_only=(_env("WTTJ_TECH_ONLY", "true") or "true").lower() in ("1", "true", "yes", "oui"),
        adzuna_app_id=_env("ADZUNA_APP_ID"),
        adzuna_app_key=_env("ADZUNA_APP_KEY"),
        adzuna_countries=_env_list("ADZUNA_COUNTRIES", "fr"),
        adzuna_keywords=_env_list(
            "ADZUNA_KEYWORDS", "data engineer,data analyst,data scientist,développeur,devops,cybersécurité"
        ),
        adzuna_max_pages=_env_int("ADZUNA_MAX_PAGES", 20),
        adzuna_max_days_old=_env_int("ADZUNA_MAX_DAYS_OLD", 0),
        ft_client_id=_env("FRANCE_TRAVAIL_CLIENT_ID"),
        ft_client_secret=_env("FRANCE_TRAVAIL_CLIENT_SECRET"),
        # codes ROME du domaine M18 "Systèmes d'information" (développement, admin/prod SI, conseil SI...)
        ft_rome_codes=_env_list("FRANCE_TRAVAIL_ROME_CODES", "M1801,M1802,M1803,M1805,M1806,M1810"),
        ft_keywords=_env_list("FRANCE_TRAVAIL_KEYWORDS", "data,devops,cybersécurité"),
        ft_since_days=_env_int("FRANCE_TRAVAIL_SINCE_DAYS", 0),
        ft_max_pages=_env_int("FRANCE_TRAVAIL_MAX_PAGES", 0),
    )
