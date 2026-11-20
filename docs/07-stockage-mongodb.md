# 07 – Stockage analytique : MongoDB

**Outils** : MongoDB 7.0, `pymongo` (bulk upserts, agrégations), MongoDB Compass (exploration)
**Code** : `pipeline/jobinsight/warehouse/mongo_loader.py`, `docker/mongo/init-mongo.js`

## Rôle
Couche **Processed / Warehouse** et base de l'application web : dernière version consolidée de
chaque offre + collections techniques (monitoring, IA, sécurité).

| Collection | Contenu |
|---|---|
| `jobs` | offres consolidées (modèle de données, doc 00) |
| `quality_reports`, `pipeline_runs` | monitoring du pipeline |
| `kpi_snapshots` | historique des KPIs globaux à chaque run |
| `ml_runs`, `ml_clusters`, `job_embeddings` | IA |
| `users`, `audit_logs` | sécurité |

## Chargement idempotent
```python
UpdateOne({"dedup_key": key}, {
    "$set": doc,                              # dernière version
    "$setOnInsert": {"first_seen_at": now},   # date de première détection
    "$max": {"last_seen_at": now},
    "$inc": {"seen_count": 1},
    "$addToSet": {"sources": {"$each": sources}},
}, upsert=True)
```
Envoyé par paquets de 1 000 (`bulk_write`, `ordered=False`).

## Cycle de vie des offres
**Code** : `pipeline/jobinsight/warehouse/lifecycle.py` · **Tâche Airflow** : `update_lifecycle`
(branche parallèle après `tag_scope`, un échec ne bloque pas les KPIs) · **Tests** : `pipeline/tests/test_lifecycle.py`

L'historisation (`first_seen_at`, `last_seen_at`) et l'historique des runs (`pipeline_runs`)
permettent de savoir si une offre est toujours en ligne. Une absence n'a pas le même sens selon
la source :

| Type de source | Sources | Une offre absente de la collecte veut dire |
|---|---|---|
| Liste complète | Remotive, python.org, France Travail | qu'elle a été **retirée** (pourvue ou abandonnée) |
| Fenêtre récente | WTTJ (sitemap des 7 derniers jours, 5 000 offres au plus), Arbeitnow (3 pages), Jobicy, Adzuna | seulement qu'elle est **sortie de la fenêtre** de collecte |

Statut écrit dans `jobs.lifecycle.status` :
- `active` : vue lors de la dernière collecte réussie de sa source
- `expired` : source à liste complète, absente des 2 dernières collectes réussies (une collecte
  manquée est tolérée, au cas où l'API aurait eu un raté)
- `out_of_window` : source à fenêtre, absente de la dernière collecte réussie

Seules les collectes **réussies et chargées** comptent : un run bloqué par la porte de qualité ne
prouve pas qu'une offre a disparu. Le même document porte aussi `age_days` (depuis la date de
publication de la source), `observed_days` (durée de suivi), `missed_runs` et `expired_at`.

À chaque run, un snapshot est ajouté dans `lifecycle_snapshots` : répartition par statut et par
source, âge médian des offres actives, offres ouvertes depuis plus de 30 jours, nouvelles offres et
offres expirées sur 24 h, durée de vie médiane des offres expirées, et âge médian par périmètre
Tech/Data, ville, niveau d'expérience et type de contrat (groupes d'au moins 20 offres). Le secteur
(`industry`, rempli à 6 %) n'est pas retenu.

Premier calcul, le 20/11/2026 sur 14 434 offres (1,8 s) : 6 141 actives, 8 291 sorties de fenêtre,
2 expirées. Sans cette distinction, 8 293 offres auraient été annoncées comme retirées à tort. Les
indicateurs d'âge deviennent plus parlants avec l'historique et avec France Travail, source à liste
complète dont les offres restent en ligne plusieurs semaines.

## Index
| Index | Usage |
|---|---|
| `dedup_key` **unique** | dédup inter-lots |
| `publication_date` (desc) | tri, filtres de période, timeline |
| `country`, `contract_type`, `experience_level`, `industry`, `sources`, `technologies`, `skills`, `remote`, `cluster_id` | filtres du dashboard |
| index **texte** pondéré (titre ×10, entreprise ×5, description ×1) | recherche plein texte |
| `lifecycle.status` | filtre offres actives, expirées, hors fenêtre |

## KPIs par agrégation (API)
Exemple « Top technologies » :
```js
[{ $match: filtres }, { $unwind: "$technologies" },
 { $group: { _id: "$technologies", jobs: { $sum: 1 } } }, { $sort: { jobs: -1 } }, { $limit: 15 }]
```
La vue d'ensemble utilise `$facet` (8 indicateurs en une seule requête), la distribution des
salaires `$bucket`.

## Sécurité
- `--auth` activé ; **un utilisateur par usage** (`init-mongo.js`) : `jobinsight_pipeline`
  (readWrite), `jobinsight_api` (readWrite), `jobinsight_bi` (**lecture seule**, pour Compass /
  Power BI). Le compte root n'est utilisé par aucun service.
- Port publié uniquement sur `127.0.0.1`.

## Explorer avec Compass
`mongodb://jobinsight_bi:<MONGO_BI_PASSWORD>@localhost:27018/jobinsight?authSource=jobinsight`
