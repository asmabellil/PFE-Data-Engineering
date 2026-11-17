# Guide Power BI – rapport « JobCompass Analytics »

Pré-requis : Power BI Desktop (gratuit, Microsoft Store) et au moins un run du DAG
`jobinsight_pipeline` (les CSV apparaissent dans `D:\DSP\PFE\exports\`).

## 1. Importer les données (≈ 5 min)
1. *Accueil → Obtenir les données → Texte/CSV* → importer :
   `fact_jobs.csv`, `bridge_job_technology.csv`, `bridge_job_skill.csv`, `dim_technology.csv`, `dim_skill.csv`
   (+ `kpi_salary_by_experience.csv` si besoin).
2. Pour chaque fichier : *Transformer les données* → vérifier **Origine du fichier = 65001 : Unicode (UTF-8)**.
3. Types dans Power Query : `publication_date` → **Date** ; `salary_*`, `completeness` → **Nombre décimal** ;
   `remote` → **Vrai/Faux**. *Fermer et appliquer*.

> Mise à jour : *Actualiser* relit les CSV régénérés à chaque run. Pour éviter les chemins absolus,
> créer un paramètre `DossierExports` = `D:\DSP\PFE\exports\`.

## 2. Modèle en étoile (vue Modèle)
| De | Vers | Cardinalité | Filtrage |
|---|---|---|---|
| `bridge_job_technology[dedup_key]` | `fact_jobs[dedup_key]` | * → 1 | **les deux sens** |
| `bridge_job_technology[technology]` | `dim_technology[technology]` | * → 1 | simple |
| `bridge_job_skill[dedup_key]` | `fact_jobs[dedup_key]` | * → 1 | **les deux sens** |
| `bridge_job_skill[skill]` | `dim_skill[skill]` | * → 1 | simple |
| `fact_jobs[publication_date]` | `Calendrier[Date]` | * → 1 | simple |

Table calendrier (*Modélisation → Nouvelle table*) :
```DAX
Calendrier =
ADDCOLUMNS (
    CALENDAR ( MIN ( fact_jobs[publication_date] ), MAX ( fact_jobs[publication_date] ) ),
    "Année", YEAR ( [Date] ),
    "Mois", FORMAT ( [Date], "yyyy-mm" ),
    "Semaine", WEEKNUM ( [Date], 2 ),
    "Jour semaine", FORMAT ( [Date], "dddd" )
)
```
Marquer comme table de dates.

## 3. Mesures DAX (table `fact_jobs` → *Nouvelle mesure*)
```DAX
Nb offres = DISTINCTCOUNT ( fact_jobs[dedup_key] )
Nb entreprises = DISTINCTCOUNT ( fact_jobs[company] )
Nb pays = DISTINCTCOUNT ( fact_jobs[country] )
Nb technologies = DISTINCTCOUNT ( bridge_job_technology[technology] )
% télétravail = DIVIDE ( CALCULATE ( [Nb offres], fact_jobs[remote] = TRUE () ), [Nb offres] )
Salaire médian (€) =
    MEDIANX ( FILTER ( fact_jobs, NOT ISBLANK ( fact_jobs[salary_mid_eur] ) ), fact_jobs[salary_mid_eur] )
Salaire moyen (€) = AVERAGE ( fact_jobs[salary_mid_eur] )
% offres avec salaire =
    DIVIDE ( CALCULATE ( [Nb offres], NOT ISBLANK ( fact_jobs[salary_mid_eur] ) ), [Nb offres] )
Part des offres (%) =
    DIVIDE ( [Nb offres], CALCULATE ( [Nb offres], ALL ( dim_technology ) ) )
Offres 30 j =
    CALCULATE ( [Nb offres], DATESINPERIOD ( Calendrier[Date], MAX ( Calendrier[Date] ), -30, DAY ) )
Offres 30 j précédents =
    CALCULATE ( [Nb offres], DATESINPERIOD ( Calendrier[Date], MAX ( Calendrier[Date] ) - 30, -30, DAY ) )
Évolution 30 j (%) = DIVIDE ( [Offres 30 j] - [Offres 30 j précédents], [Offres 30 j précédents] )
Complétude moyenne = AVERAGE ( fact_jobs[completeness] )
```
Formats : pourcentages en %, salaires en « 0 € ».

## 4. Pages du rapport
**Page 1 – Vue d'ensemble**
- 4 cartes : Nb offres, Nb entreprises, Nb technologies, Nb pays (+ Évolution 30 j en sous-titre)
- Graphique en aires : Nb offres par `Calendrier[Date]`
- Anneau : Nb offres par `industry` (top 7)
- Carte remplie (*Filled map*) : `country` (définir *Catégorie de données = Pays*)
- Segments : pays, période (`Calendrier[Date]`), source

**Page 2 – Compétences & technologies**
- Barres horizontales : Nb offres par `dim_technology[technology]` (Top N = 20)
- Matrice : `tech_category` × `technology` avec Nb offres, Part des offres (%)
- Barres : Nb offres par `dim_skill[skill]`, segment `skill_category`
- Courbes : Nb offres par mois pour 5 technologies (segment multi-sélection)

**Page 3 – Salaires & contrats**
- Cartes : Salaire médian, % offres avec salaire
- Histogramme : `salary_mid_eur` (groupes de 10 000)
- Barres : Salaire médian par `experience_level`, par technologie (filtre ≥ 3 offres)
- Anneau : Nb offres par `contract_type`
- Tableau : pays, Nb offres, Salaire moyen

**Page 4 (option) – Qualité des données** : Complétude moyenne, Nb offres par `source`,
`industry_source` (source vs prédit par ML).

## 5. Mise en forme
Thème : *Affichage → Thèmes* → couleur principale `#2563EB` (identique au front React).
Une seule couleur pour les barres simples ; légende dès qu'il y a plusieurs séries ;
titres explicites (« Top 20 des technologies demandées »).

## 6. À mettre dans le rapport
Capture de la vue Modèle (étoile), des 3 pages, et l'extrait DAX de 2-3 mesures.
