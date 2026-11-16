# 06 – Data Quality et déduplication

**Outils** : règles Python (`quality.py`), Spark (window functions, agrégations), MongoDB (upsert)

## Contrôles (Livrable 1 §12)

| Dimension | Code | Gravité | Règle |
|---|---|---|---|
| Complétude | `MISSING_TITLE`, `MISSING_COMPANY`, `MISSING_URL` | **bloquant** | champ obligatoire absent |
| Complétude | `MISSING_DESCRIPTION`, `SHORT_DESCRIPTION`, `MISSING_LOCATION` | avertissement | |
| Validité | `SALARY_MIN_GT_MAX` | **bloquant** | `salary_min ≤ salary_max` |
| Validité | `INVALID_URL`, `INVALID_DATE`, `FUTURE_DATE` | **bloquant** | format / date incohérente |
| Unicité | contrôle global | rapport | `job_id` et `dedup_key` uniques après dédup |
| Fraîcheur | `STALE_OFFER` | avertissement | publiée il y a plus de 90 jours |
| Cohérence | `COUNTRY_MISMATCH` | avertissement | pays déduit de la ville ≠ pays annoncé |
| Robustesse | `TRANSFORM_ERROR` | **bloquant** | exception pendant la transformation |

- Bloquant → **zone `quarantine/`** : le pipeline n'est pas bloqué (Livrable 1 §12) et les offres
  peuvent être analysées / retraitées plus tard.
- Score de **complétude** (0-1) calculé pour chaque offre.

## Rapport qualité (par lot)
Stocké dans `reports/quality/<run>.json` (MinIO) et `quality_reports` (MongoDB), affiché dans la
page « Pipeline & qualité » :
```json
{"records_total": 1480, "records_valid": 1452, "records_quarantine": 28,
 "duplicates_removed": 61, "records_processed": 1391, "uniqueness_ok": true,
 "avg_completeness": 0.81,
 "issues": [{"code": "MISSING_DESCRIPTION", "dimension": "Complétude", "count": 18}, ...]}
```
*(valeurs illustratives – remplacer par celles de votre run dans le rapport)*

## Déduplication à 3 niveaux (Livrable 1 §10.5)

1. **Dans la source** (collecteur) : même `source_id` vu deux fois dans un run → ignoré.
2. **Entre sources, dans un lot** (Spark) :
   ```python
   dedup_key = sha1(norm_company(company) | norm(title) | norm(city or country or "remote"))
   w = Window.partitionBy("dedup_key").orderBy(desc("completeness"), desc("collected_at"))
   ```
   On garde **la version la plus complète** ; `sources` = liste de toutes les plateformes où
   l'offre apparaît. La normalisation ignore la casse, les accents, la ponctuation, les mentions
   `(m/w/d)` / `(H/F)` et les suffixes juridiques (`GmbH`, `SAS`, `Inc`…).
3. **Entre lots** (MongoDB) : upsert sur `dedup_key` (index unique) avec
   `$setOnInsert first_seen_at`, `$max last_seen_at`, `$inc seen_count`, `$addToSet sources`.

La date de publication n'est volontairement pas dans la clé : elle diffère souvent d'une source à
l'autre pour la même offre ; l'historisation est assurée par `first_seen_at` / `last_seen_at`.

## Indicateurs globaux
`GET /api/admin/quality-summary` : taux de complétude par attribut, nombre d'offres vues sur
plusieurs sources, quarantaine et doublons des 10 derniers lots.
