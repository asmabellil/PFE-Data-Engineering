# 11 – Visualisation Power BI

**Outils** : Power BI Desktop (Windows, gratuit), exports CSV produits par Spark
**Guide pas à pas** : [`powerbi/GUIDE_POWERBI.md`](../powerbi/GUIDE_POWERBI.md)

## Rôle
Le front React est l'application des utilisateurs (étudiants, recruteurs) ; **Power BI** est l'outil
de **reporting des analystes / managers** (Livrable 1 §5) : exploration libre, export, partage.

## Source de données : modèle en étoile
La tâche `spark_analytics_kpis` écrit à chaque run dans `exports/` :

| Fichier | Rôle dans le modèle |
|---|---|
| `fact_jobs.csv` | **table de faits** (1 ligne = 1 offre consolidée) |
| `bridge_job_technology.csv`, `bridge_job_skill.csv` | tables de liaison (offre ↔ techno / compétence) |
| `dim_technology.csv`, `dim_skill.csv` | dimensions (catégorie) |
| `kpi_*.csv` | agrégats gold déjà calculés par Spark (option rapide) |

```
dim_technology 1──* bridge_job_technology *──1 fact_jobs 1──* bridge_job_skill *──1 dim_skill
                                                    │
                                              Date (table calendrier DAX)
```
Encodage UTF-8 avec BOM (accents corrects dans Power BI / Excel).

Alternative « temps réel » : connecteur ODBC MongoDB avec l'utilisateur **lecture seule**
`jobinsight_bi` (voir doc 07).
