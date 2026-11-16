# 10 – Frontend : application React

**Outils** : React 18, Vite 5 (build), React Router 6, **Recharts** (graphiques), CSS natif
(thème clair / sombre automatique), nginx (service en production)
**Code** : `frontend/src/` · **URL** : http://localhost:3000 (dev : `npm run dev` → http://localhost:5173)

## Pages (inspirées de la maquette JobInsight du Livrable 1, Figure 2)

| Page | Contenu | Endpoints |
|---|---|---|
| **Connexion / inscription** | formulaire, politique de mot de passe | `/auth/*` |
| **Tableau de bord** | 4 cartes KPI (offres + tendance, entreprises, technologies, pays), évolution (jour/semaine/mois), donut des secteurs, top technologies, offres par pays, dernières offres | `/analytics/*`, `/jobs` |
| **Offres d'emploi** | recherche plein texte, 8 filtres, tri, pagination, fiche détaillée (compétences, salaire, **lien vers la source**) | `/jobs` |
| **Analyses** | contrats, expérience, villes, sources, salaires (distribution, par niveau, par technologie, par pays) | `/analytics/*` |
| **Compétences** | top 25 technologies, compétences techniques / soft skills / langues, technologies par catégorie, évolution des 5 premières | `/analytics/*` |
| **IA & matching** | matching CV, recherche sémantique, estimation de salaire, classification ML vs DL, métriques des modèles, clusters | `/ai/*` |
| **Pipeline & qualité** (analyst+) | complétude, dernier rapport qualité, exécutions, utilisateurs et journal d'audit (admin) | `/admin/*` |

Filtres **globaux** (pays, période) dans la barre supérieure, appliqués à toutes les pages.

## Architecture
```
src/
├── api.js            client fetch (JWT, gestion 401), libellés FR, formats
├── context.jsx       AuthProvider, FilterProvider, hook useApi
├── App.jsx           routes + garde d'accès par rôle
├── components/       Layout (sidebar, barre de filtres), charts (Recharts), JobDrawer
└── pages/            Login, Dashboard, Jobs, Analyses, Skills, AI, Pipeline
```

## Choix de visualisation
- Une seule teinte pour les séries uniques (barres, aire) → pas de légende inutile ;
  palette catégorielle à **ordre fixe** pour les séries multiples (donut, courbes) avec légende ;
  au-delà de 7 catégories, regroupement en « Autres ».
- Info-bulles au survol sur tous les graphiques, grille discrète, jamais de double axe.
- Thème sombre automatique (`prefers-color-scheme`).

## Sécurité côté front
- Jeton en `sessionStorage` (effacé à la fermeture de l'onglet), déconnexion automatique sur 401.
- Liens externes `rel="noopener noreferrer"`.
- nginx : **Content-Security-Policy**, `X-Frame-Options: DENY`, `nosniff`, `server_tokens off` ;
  l'API est servie sous le même domaine (`/api` proxifié) → pas de CORS ouvert.

## Build
```bash
cd frontend && npm install && npm run build     # vérifié : build OK
```
