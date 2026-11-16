"""Accès au Data Lake (MinIO, compatible S3).

Organisation des zones (cf. Livrable 1 §10.3 et §13) :

    datalake/
    ├── raw/<source>/<YYYY-MM-DD>/batch_<run>.jsonl        données brutes, immuables
    ├── processed/jobs/<YYYY-MM-DD>/<run>/*.parquet        données nettoyées / dédupliquées
    ├── quarantine/<YYYY-MM-DD>/<run>/*.parquet            données non conformes (Data Quality)
    ├── gold/<kpi>/<run>/*.parquet                         agrégats analytiques (KPIs)
    ├── reports/quality/<run>.json                         rapports de qualité
    └── models/<name>/<version>                            modèles ML versionnés
"""
from __future__ import annotations

import os
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from jobinsight.config import Settings, get_settings
from jobinsight.utils import get_logger

log = get_logger("lake")


class DataLake:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.bucket = self.settings.lake_bucket
        self.s3 = boto3.client(
            "s3",
            endpoint_url=self.settings.minio_endpoint,
            aws_access_key_id=self.settings.minio_access_key,
            aws_secret_access_key=self.settings.minio_secret_key,
            config=Config(signature_version="s3v4", retries={"max_attempts": 5}),
            region_name="us-east-1",
        )

    def ensure_bucket(self) -> None:
        try:
            self.s3.head_bucket(Bucket=self.bucket)
        except ClientError:
            log.info("création du bucket %s", self.bucket)
            self.s3.create_bucket(Bucket=self.bucket)
            # versioning activé : historisation + protection contre l'écrasement accidentel
            self.s3.put_bucket_versioning(
                Bucket=self.bucket, VersioningConfiguration={"Status": "Enabled"}
            )

    # ------------------------------------------------------------ I/O
    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream"):
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        log.info("écrit s3://%s/%s (%s octets)", self.bucket, key, len(data))

    def get_bytes(self, key: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return keys

    def upload_dir(self, local_dir: str | Path, prefix: str, suffixes=(".parquet", ".json", ".csv")):
        local_dir = Path(local_dir)
        n = 0
        for path in local_dir.rglob("*"):
            if path.is_file() and path.suffix in suffixes:
                key = f"{prefix.rstrip('/')}/{path.relative_to(local_dir).as_posix()}"
                self.s3.upload_file(str(path), self.bucket, key)
                n += 1
        log.info("upload %s fichiers -> s3://%s/%s", n, self.bucket, prefix)
        return n

    def download_prefix(self, prefix: str, local_dir: str | Path, suffix: str = "") -> list[str]:
        local_dir = Path(local_dir)
        paths = []
        for key in self.list_keys(prefix):
            if suffix and not key.endswith(suffix):
                continue
            dest = local_dir / key
            os.makedirs(dest.parent, exist_ok=True)
            self.s3.download_file(self.bucket, key, str(dest))
            paths.append(str(dest))
        return paths


def raw_key(source: str, date: str, run_id: str) -> str:
    return f"raw/{source}/{date}/batch_{run_id}.jsonl"
