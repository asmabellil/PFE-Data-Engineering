# 03 – Orchestration : Apache Airflow

**Outils** : Apache Airflow 2.10.4 (LocalExecutor, métadonnées PostgreSQL 16), TaskFlow API
**Code** : `airflow/dags/jobinsight_pipeline.py`, `airflow/dags/jobinsight_ml.py`, `airflow/Dockerfile`
**Interface** : http://localhost:8080 (identifiants `AIRFLOW_ADMIN_*` du `.env`)

## DAG `jobinsight_pipeline` (toutes les 6 heures)

```
collect_arbeitnow ┐
collect_jobicy    │
collect_remotive  ├─► ingest_to_datalake ─► spark_etl_quality ─► load_mongodb ─► ml_enrich_industry
collect_pythonorg │      (ALL_DONE)                                                      │
collect_adzuna    │                                                                      ▼
collect_france_tr.┘                                    refresh_semantic_index ◄── spark_analytics_kpis
```

| Tâche | Rôle |
|---|---|
| `collect_<source>` | collecte + publication Kafka (en parallèle) ; `skipped` si clé API absente |
| `ingest_to_datalake` | Kafka → MinIO raw ; `trigger_rule=ALL_DONE` : s'exécute même si une source a échoué |
| `spark_etl_quality` | job Spark : nettoyage, enrichissement, Data Quality, dédup → processed / quarantine |
| `load_mongodb` | upsert idempotent dans l'entrepôt |
| `ml_enrich_industry` | prédiction du secteur manquant par le modèle ML |
| `spark_analytics_kpis` | KPIs Spark SQL → gold/ + exports CSV Power BI + snapshot KPI |
| `refresh_semantic_index` | demande au backend d'encoder les nouvelles offres (Deep Learning) |

### Bonnes pratiques mises en œuvre
- **Planification** `0 */6 * * *` : 4 runs / jour (respect des CGU Remotive).
- `catchup=False`, `max_active_runs=1` : pas d'exécutions concurrentes.
- **Retries** : 2 par tâche avec backoff exponentiel ; `execution_timeout` 45 min.
- **Rejouable / idempotent** : l'identifiant de lot est `ts_nodash` ; relancer un run (*Clear*)
  retraite les mêmes fichiers raw ; l'upsert MongoDB ne crée pas de doublon.
- **Monitoring** : chaque tâche écrit ses statistiques dans `pipeline_runs` (MongoDB), callback
  `on_failure_callback` pour tracer les échecs → page « Pipeline & qualité » du front.
- Documentation du DAG (`doc_md`) visible dans l'interface Airflow.

## DAG `jobinsight_ml` (chaque lundi 3h)
`train_category_classifier → predict_missing_industries`, `train_salary_model`,
`train_job_clusters → train_deep_learning` (déclenché sur le backend qui possède PyTorch).

## Image Docker
L'image officielle `apache/airflow:2.10.4-python3.11` est étendue avec **Java 17** (requis par Spark)
et le package `jobinsight` installé en mode *editable* : le dossier `pipeline/` est monté en volume,
donc une modification du code est prise en compte sans reconstruire l'image.

## Commandes utiles
```bash
docker compose exec airflow airflow dags list
docker compose exec airflow airflow dags trigger jobinsight_pipeline
docker compose exec airflow airflow tasks test jobinsight_pipeline collect_jobicy 2026-11-16
docker compose logs -f airflow
```
