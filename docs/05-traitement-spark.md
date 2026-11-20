# 05 – Traitement : Apache Spark (nettoyage, transformation, enrichissement)

**Outils** : Apache Spark 3.5.8 (**PySpark**), Java 17, Spark SQL, window functions
**Code** : `pipeline/jobinsight/processing/` (`spark_etl.py` + fonctions pures testées)

## Déroulé du job `spark_etl`

```
raw JSONL ──textFile──► RDD[str] ──map(safe_transform)──► DataFrame (schéma typé, 35 colonnes)
   │                                                              │
   │                       ┌──────────── dq_status == valid ──────┴──── sinon ──► quarantine/
   │                       ▼
   │     Window(partitionBy dedup_key, orderBy completeness desc, collected_at desc) → row_number = 1
   │                       ▼
   └──────────────► processed/ (Parquet) + rapport qualité JSON
```

`safe_transform` applique, **pour chaque offre et en parallèle sur les cœurs** :

| Étape | Module | Exemples |
|---|---|---|
| 1. Standardisation | `standardize.py` | 6 formats source → 1 schéma commun |
| 2. Nettoyage texte | `cleaning.py` | HTML retiré, entités décodées, espaces uniformisés, caractères de contrôle supprimés, **e-mails / téléphones masqués** |
| 3. Dates | `cleaning.parse_date` | timestamp Unix, ISO 8601… → `YYYY-MM-DD` |
| 4. Contrat | `normalize_contract` | « Unbefristeter Arbeitsvertrag », « CDI », « Full-time permanent » → `full_time` ; « CDD », « fixed term » → `temporary` |
| 5. Expérience | `normalize_experience`, `extract_years_experience` | « berufserfahren », « Senior », « 5+ years of experience » → niveau |
| 6. Géographie | `geo.py` | « 75 - Paris 15e » → Paris / France ; « Berlin » → Allemagne ; détection télétravail |
| 7. Salaire | `salary.py` | « $3.5k–$5k/month » → 3500-5000 USD mensuel → **annualisé en EUR** ; aberrations rejetées |
| 8. NLP compétences | `skills.py` | ~110 technologies + ~35 compétences (FR / EN / DE) par regex |
| 9. Secteur | `categories.py` | 12 familles de métiers ; manquant → modèle ML |
| 10. Clés | `transform.py` | `job_id`, `dedup_key` |
| 11. Qualité | `quality.py` | codes d'anomalie + statut valid / quarantine |

Une erreur sur une offre ne fait **jamais** échouer le job : l'offre part en quarantaine avec le
code `TRANSFORM_ERROR` et le message d'erreur.

## Extraction de compétences (NLP)
Taxonomie contrôlée `nom canonique → (catégorie, alias regex)` :
```python
"Apache Spark": ("Data / Big Data", [r"\bspark\b", r"pyspark"]),
"Java": ("Langage", [r"java(?!\s*script)"]),        # ne capte pas JavaScript
"Travail en équipe": ("Comportementale", [r"team ?work", r"travail en [ée]quipe", r"teamf[äa]hig"]),
```
Garde-fous contre les faux positifs (« Go » dans « Google », « Java » dans « JavaScript »),
testés unitairement. Approche explicable et multilingue ; complétée par l'IA (doc 08).

## Pourquoi des fonctions Python pures + Spark ?
Les règles métier sont des fonctions Python **testables sans Spark** (38 tests pytest) ; Spark
apporte la parallélisation, le schéma typé, les window functions, les agrégations SQL et
l'écriture Parquet. Le même job tourne sur un cluster en changeant `SPARK_MASTER`.

## Lancer à la main
```bash
docker compose exec airflow python -m jobinsight.processing.spark_etl --run-id <ts_nodash>
```

## Résultats observés (échantillon réel du 16/11/2026, 438 offres)
- 100 % des offres Arbeitnow / Jobicy / Remotive valides ; 18 fiches python.org sans description
  détaillée (limite volontaire de pages scrapées) → avertissement `MISSING_DESCRIPTION`.
- Top technologies : Python, CI/CD, LLM, SQL, AWS, Azure, Docker, Kubernetes.
- 68 offres avec salaire exploitable (Jobicy + Remotive).
