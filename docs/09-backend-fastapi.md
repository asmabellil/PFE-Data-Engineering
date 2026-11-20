# 09 – Backend : API FastAPI

**Outils** : FastAPI 0.115, Uvicorn, Pydantic v2, PyMongo, PyJWT, bcrypt, SlowAPI, pytest + mongomock
**Code** : `backend/app/` · **Documentation interactive** : http://localhost:8000/docs (Swagger / OpenAPI)

## Structure
```
backend/app/
├── main.py          app, middlewares (CORS, en-têtes de sécurité), bootstrap admin, /api/health
├── config.py        configuration par variables d'environnement (pydantic-settings)
├── security.py      bcrypt, JWT, RBAC, jeton de service, audit
├── filters.py       filtres MongoDB typés (anti-injection)
├── limiter.py       rate limiting
├── routers/         auth · jobs · analytics · ai · admin
└── ai/              semantic.py (Transformer) · train_dl.py (PyTorch)
```

## Endpoints

| Méthode | Route | Rôle min. | Description |
|---|---|---|---|
| POST | `/api/auth/register` · `/api/auth/login` | public | inscription (rôle viewer) / connexion → JWT |
| GET | `/api/auth/me` | viewer | profil courant |
| GET | `/api/jobs` | viewer | liste paginée + filtres (q, pays, contrat, niveau, secteur, techno, source, remote, période, salaire, cycle de vie `status=active\|expired\|out_of_window`) + tri. Le filtre `status` vaut aussi pour les routes `/api/analytics/*` sauf `/kpi-history` (KPIs sur les offres encore en ligne) |
| GET | `/api/jobs/filters` · `/api/jobs/{dedup_key}` | viewer | valeurs de filtres · détail |
| GET | `/api/analytics/overview` | viewer | KPIs (`$facet`) + tendance 30 j |
| GET | `/api/analytics/timeline?granularity=day\|week\|month` | viewer | évolution des offres |
| GET | `/api/analytics/top-technologies` · `/top-skills` | viewer | classements |
| GET | `/api/analytics/breakdown/{country\|contract\|experience\|industry\|source\|city\|cluster}` | viewer | répartitions |
| GET | `/api/analytics/salaries` · `/technology-trend` · `/kpi-history` | viewer | salaires, tendances |
| POST | `/api/ai/search` · `/match-cv` · `/classify` · `/predict-salary` | viewer | IA |
| GET | `/api/ai/models` · `/clusters` · `/status` | viewer | métriques IA |
| POST | `/api/ai/reindex` · `/train-dl` | admin **ou** jeton de service | tâches IA en arrière-plan |
| GET | `/api/admin/pipeline-runs` · `/quality-reports` · `/quality-summary` | analyst | monitoring |
| GET | `/api/admin/lifecycle` | analyst | cycle de vie des offres : dernier snapshot et évolution sur les derniers runs |
| GET | `/api/admin/contract-rejections` | analyst | contrat de données : offres publiées et rejetées (file `jobs.dlq`) par run et par source, raisons les plus fréquentes |
| GET/PATCH | `/api/admin/users` · `/users/{email}/role` · `/audit` | admin | administration |

Tous les endpoints analytiques acceptent les **mêmes filtres globaux** que la liste des offres :
le filtre « pays / période » de la barre du haut s'applique à tout le dashboard.

## Points techniques
- Endpoints synchrones (`def`) exécutés dans le pool de threads de FastAPI (PyMongo est synchrone).
- Validation stricte : `page_size ≤ 100`, longueurs max, `pattern` regex sur les énumérations.
- Erreurs non gérées → `500 {"detail": "Erreur interne"}` sans stacktrace (journalisée côté serveur).
- Compte administrateur créé au démarrage depuis `ADMIN_EMAIL` / `ADMIN_PASSWORD`.
- Conteneur exécuté avec un **utilisateur non-root**, healthcheck sur `/api/health`.

## Tests (`backend/tests/test_api.py`)
Routes protégées (401), politique de mot de passe, hachage, doublon d'e-mail (409), jeton
falsifié rejeté, RBAC (403), filtres et **tentative d'injection NoSQL neutralisée**, en-têtes de
sécurité, jeton de service.
```bash
cd backend && pip install -r requirements.txt -r requirements-dev.txt -e ../pipeline && pytest -q
```
