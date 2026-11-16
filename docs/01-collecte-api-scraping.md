# 01 – Collecte des données : API et Web Scraping

**Outils** : Python 3.11, `requests` (+ `urllib3.Retry`), `BeautifulSoup 4`, `urllib.robotparser`
**Code** : `pipeline/jobinsight/collectors/`

## Sources retenues

| Source | Type | Clé | Volume / run | Particularités |
|---|---|---|---|---|
| Arbeitnow | API REST publique | non | ~900 (3 pages × 300) | Europe (Allemagne surtout), pas de secteur → prédit par ML |
| Jobicy | API REST publique | non | ~100 par région (7 régions) | niveau d'expérience, **salaires structurés** |
| Remotive | API REST publique | non | ~20-100 | catégories, salaires en texte libre ; **max 4 appels / jour** |
| python.org/jobs | **Web scraping** | non | ~20 | HTML parsé avec BeautifulSoup |
| **Welcome to the Jungle** | **Sitemap XML** | non | jusqu'à 5 000 (`WTTJ_MAX_JOBS`) | offres françaises ; entreprise, intitulé, ville, date extraits de l'URL ; pas de description |
| Adzuna | API REST | oui (gratuite) | ~300 | France, salaires ; activée si `ADZUNA_APP_ID/KEY` |
| France Travail | API REST OAuth2 | oui (gratuite) | ~600 | France, compétences ROME ; activée si identifiants |

Conformément au Livrable 1 §10.1, **les API officielles sont privilégiées** ; le scraping n'est
utilisé que là où il est autorisé.

## Grandes plateformes : étude d'accessibilité (16/11/2026)

| Plateforme | Constat | Décision |
|---|---|---|
| LinkedIn | robots.txt : *« The use of robots or other automated means to access LinkedIn without the express permission of LinkedIn is strictly prohibited »* ; `Disallow: /jobs-guest/` ; pas d'API emploi publique | **écartée** |
| Indeed | réponse **403** (anti-robot) ; CGU interdisant le scraping ; API éditeur fermée | **écartée** |
| Welcome to the Jungle | pages de recherche interdites (`*/jobs?query=*`, `/*?`) ; **sitemap des offres publié pour les robots** ; fiches détaillées en 403 pour un robot identifié | **retenue via le sitemap uniquement** (`collectors/wttj_sitemap.py`), sans contourner la protection des fiches |

Alternative légale pour élargir la couverture : les API **Adzuna** et **France Travail** (agrégateurs) – clés gratuites.

## Architecture modulaire

```python
class BaseCollector(ABC):
    name = "base"                     # -> raw/<name>/<date>/
    def is_enabled(self): ...         # source désactivable (clé absente)
    def fetch(self): ...              # renvoie les offres brutes (payload d'origine)
    def source_id(self, payload): ... # identifiant dans la source
    def collect(self, run_id): ...    # ajoute les métadonnées -> enveloppe
```
Ajouter une source = écrire une classe et l'enregistrer dans `COLLECTORS` (`collectors/__init__.py`)
+ une fonction de mapping dans `processing/standardize.py`.

Chaque offre est emballée dans une **enveloppe** qui conserve la donnée brute intacte :
```json
{"source": "jobicy", "source_kind": "api", "source_id": "162628", "run_id": "20261116T120000",
 "collected_at": "2026-11-16T12:00:03+00:00", "payload": { ...réponse brute de l'API... }}
```

## Fiabilité / gestion des erreurs
- Session HTTP avec **retries exponentiels** sur 429 / 5xx et respect de l'en-tête `Retry-After`.
- Timeouts systématiques (30 s).
- Une région / page en échec est journalisée sans bloquer les autres.
- Dédoublonnage interne à la source (même offre sur deux pages).
- Pause configurable entre requêtes (`REQUEST_DELAY_S`).
- Dans Airflow : une tâche par source, 2 retries ; une source en panne n'empêche pas le pipeline.

## Web scraping éthique et légal (python.org)
1. **robots.txt vérifié automatiquement** avant chaque URL (`urllib.robotparser`) – `/jobs/` est autorisé.
2. **User-Agent explicite** identifiant le projet étudiant.
3. **Débit limité** : 1 requête/seconde, nombre de pages et de fiches détaillées plafonné.
4. **Minimisation RGPD** : la section « Contact Info » (nom, e-mail du recruteur) est **supprimée
   avant stockage** ; les e-mails / téléphones restants sont masqués au nettoyage.
5. Les offres ne sont jamais republiées : le front renvoie toujours vers l'URL d'origine et cite
   la source (exigé par les CGU de Remotive et Jobicy).

Extrait :
```python
def parse_list(html):
    soup = BeautifulSoup(html, "html.parser")
    for li in soup.select("ol.list-recent-jobs > li"):
        link = li.select_one(".listing-company-name a")
        ...
```

## Lancer une collecte à la main
```bash
docker compose exec airflow python -m jobinsight.cli collect --run-id test1 --source jobicy
```

## Tests
`pipeline/tests/test_processing.py::test_pythonorg_parser_removes_contact_section` vérifie la suppression
des données personnelles du scraper.
