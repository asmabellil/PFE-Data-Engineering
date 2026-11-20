# 🗺️ Roadmap – JobCompass (PFE M2 Data Engineering)

> **Projet** : plateforme Big Data de collecte et d'analyse des offres d'emploi
> **Équipe** : Asma BELLIL · Ghaylene DRIDI · Mohamed Yacine BRAHMIA
> **Échéance** : **4 décembre 2026** – rapport + présentation + simulation vidéo
> **Point de départ** : 16 novembre 2026 (≈ 18 jours)

Légende : ✅ fait · 🟡 fait, à vérifier / lancer par l'équipe · ⬜ à faire ·
🤖 réalisé par Claude (code) · 👤 réalisé par l'équipe (Claude aide : texte, guide, relecture)

---

## 0. Ce qui est attendu (d'après la consigne)

| Livrable | Contenu exigé | Où le trouver / le produire |
|---|---|---|
| **Rapport** | Introduction · **Stocker** · **Analyser** · **Visualiser** · **Sécurité** · **IA** (analyse de données) · Conclusion (apport du projet, maîtrise de la data engineering) | Plan détaillé §5 ci-dessous ; la matière technique est dans [`docs/`](docs/) |
| **Présentation** | Présentation du projet + à la fin 2-3 slides sur le stage / l'alternance | §6 |
| **Simulation (vidéo)** | Démo du pipeline et de l'application | Script §7 |

---

## 1. Architecture réalisée (rappel)

```
APIs (Arbeitnow, Jobicy, Remotive, Adzuna*, France Travail*) + Scraping (python.org)
        │  collecteurs Python (requests / BeautifulSoup)
        ▼
Apache Kafka (topic jobs.raw)                       ← Ingestion
        ▼
MinIO – Data Lake  raw/ → processed/ → gold/        ← Stockage brut / traité
        ▼
Apache Spark (PySpark) : nettoyage, normalisation,  ← Traitement + Data Quality
NLP compétences, Data Quality, déduplication
        ▼
MongoDB – entrepôt / couche de service              ← Stockage analytique
        ▼                     ▼                       ▼
FastAPI (JWT, RBAC) → React   Exports CSV → Power BI   IA : scikit-learn + Transformers/PyTorch
        ▲
Apache Airflow orchestre tout (DAG toutes les 6 h + DAG ML hebdomadaire) – Docker Compose
(* sources activées si vous fournissez une clé API gratuite)
```

### Écarts assumés par rapport au Livrable 1 (à justifier dans le rapport)

| Livrable 1 | Réalisé | Justification |
|---|---|---|
| Data Warehouse BigQuery / Snowflake | **MongoDB** | Demande de l'équipe (stack React / FastAPI / MongoDB) ; gratuit, local, schéma flexible adapté aux offres hétérogènes ; les KPIs « entrepôt » sont aussi produits en Parquet (zone gold) |
| Cluster Spark | **Spark en mode local[*]** dans le conteneur Airflow | Volume du MVP (quelques milliers d'offres) ; même code exécutable sur un cluster en changeant `SPARK_MASTER` |
| Streaming éventuel | **Batch via Kafka** | Conforme au §10.2 (« batch privilégié pour le MVP ») ; Kafka permet de passer au streaming sans changer les collecteurs |
| Dashboard Power BI / React | **Les deux** | React = application web sécurisée ; Power BI = reporting analyste (exports CSV en modèle en étoile) |

---

## 2. Planning (sprints courts – 18 jours)

| Sprint | Dates | Objectif | Statut | Qui |
|---|---|---|---|---|
| **S1 – Socle** | 16–17 nov | Arborescence, Docker Compose, conventions, `.env`, Git | ✅ code · ⬜ dépôt GitLab | 🤖 + 👤 |
| **S2 – Collecte & ingestion** | 17–19 nov | 6 collecteurs (4 sans clé), Kafka producer/consumer, zone Raw MinIO | ✅ code · 🟡 tester dans Docker | 🤖 |
| **S3 – Traitement & qualité** | 19–22 nov | Job Spark : nettoyage, NLP, salaires, géo, Data Quality, quarantaine, dédup ; chargement MongoDB | ✅ code (38 tests OK) · 🟡 run Docker | 🤖 |
| **S4 – Analyse** | 22–24 nov | Spark SQL → KPIs (gold) + exports Power BI ; API analytics | ✅ code · 🟡 | 🤖 |
| **S5 – Visualisation** | 24–27 nov | Front React (dashboard, offres, analyses, compétences, IA, pipeline) ; **rapport Power BI** | ✅ React · ⬜ Power BI | 🤖 / 👤 |
| **S6 – IA** | 25–28 nov | ML : classif. secteur, salaire, clustering ; DL : recherche sémantique, matching CV, MLP PyTorch | ✅ code · 🟡 entraîner sur vraies données | 🤖 |
| **S7 – Sécurité & tests** | 27–29 nov | JWT, RBAC, bcrypt, rate limiting, audit, en-têtes, moindre privilège Mongo, RGPD | ✅ code (8 tests API OK) | 🤖 |
| **S8 – Données & stabilisation** | 22 nov → 2 déc | Laisser tourner le DAG (toutes les 6 h) pour accumuler l'historique ; corriger les anomalies | ⬜ | 👤 (+🤖 corrections) |
| **S9 – Livrables** | 28 nov → 4 déc | Rapport, slides, vidéo, répétition | ⬜ | 👤 (+🤖 rédaction) |

> ⚠️ **Conseil important** : démarrez la plateforme **le plus tôt possible** (idéalement avant le 20 nov).
> Le DAG collecte toutes les 6 h : plus il tourne longtemps, plus les courbes d'évolution et les
> modèles ML seront intéressants dans le rapport et la vidéo.

---

## 3. Étapes pas à pas

### Étape 0 – Débloquer la machine (👤, 15 min) ⚠️ BLOQUANT
Le disque **C: est plein (0 Go libre)** : Docker Desktop ne peut télécharger aucune image.
1. Libérer ≥ 25 Go sur C: **ou** déplacer le disque de Docker sur D: :
   Docker Desktop → *Settings* → *Resources* → *Advanced* → *Disk image location* → `D:\DockerData` → *Apply & restart*.
2. Docker Desktop → *Settings* → *Resources* : allouer **≥ 8 Go de RAM** et 4 CPU.

### Étape 1 – Lancer la plateforme (👤 avec 🤖)
```powershell
cd D:\DSP\PFE
docker compose up -d --build          # 1er build ≈ 10-15 min (images Airflow + PyTorch)
docker compose ps                     # tous les services "healthy"/"running"
```
Le fichier `.env` (secrets aléatoires) a déjà été généré. Identifiants : voir `.env`
(`AIRFLOW_ADMIN_*`, `ADMIN_EMAIL` / `ADMIN_PASSWORD`).

| Interface | URL |
|---|---|
| Application React | https://localhost (HTTPS via Caddy) |
| API (Swagger) | http://localhost:8000/docs |
| Airflow | http://localhost:8080 |
| MinIO (Data Lake) | http://localhost:9001 |
| Kafka UI (optionnel) | `docker compose --profile admin up -d kafka-ui` → http://localhost:8081 |

### Étape 2 – Premier run du pipeline (🟡)
Airflow → DAG `jobinsight_pipeline` → ▶ *Trigger*. Vérifier chaque tâche (vert), puis :
MinIO (`datalake/raw`, `processed`, `gold`), MongoDB (collection `jobs`), le front (dashboard rempli).
Envoyer à Claude les logs de toute tâche rouge → correction.

### Étape 3 – Entraîner l'IA (🟡, après ≥ 2-3 runs)
Airflow → DAG `jobinsight_ml` → ▶ *Trigger*. Puis page **IA → Modèles** dans le front.
Le premier appel IA télécharge le modèle Transformer (~470 Mo, une seule fois).

### Étape 4 – (Optionnel, recommandé) Sources françaises (👤, 10 min)
Créer des clés gratuites → les mettre dans `.env` → `docker compose up -d airflow` :
- Adzuna : https://developer.adzuna.com (offres France, avec salaires)
- France Travail : https://francetravail.io → application → API « Offres d'emploi v2 »

### Étape 5 – Power BI (👤, guidé par [`powerbi/GUIDE_POWERBI.md`](powerbi/GUIDE_POWERBI.md))
Importer les CSV de `exports/`, créer le modèle en étoile + mesures DAX fournies, 3 pages de rapport.

### Étape 6 – Git / GitLab (👤)
```bash
git init && git checkout -b main && git add . && git commit -m "JobCompass MVP"
git checkout -b develop
git remote add origin <url-gitlab> && git push -u origin main develop
```
Branches `feature/*` comme prévu au Livrable 1 §19.2. **Ne jamais committer `.env`** (déjà dans `.gitignore`).

### Étape 7 – Livrables (👤 + 🤖) → §5, §6, §7

---

## 4. Ce que Claude peut / ne peut pas faire

| Tâche | Claude | Comment Claude vous aide sinon |
|---|---|---|
| Code du pipeline, API, front, IA, Docker, tests | ✅ fait | Corrections à partir de vos logs / captures |
| Documentation technique (`docs/`) | ✅ fait | – |
| Lancer Docker / laisser tourner le pipeline des jours | ❌ (votre machine, disque C: plein) | Commandes exactes + diagnostic des erreurs |
| Créer les clés API Adzuna / France Travail | ❌ (compte personnel) | Procédure pas à pas (Étape 4) |
| Construire le fichier **Power BI .pbix** | ❌ (logiciel graphique Windows) | Guide complet : modèle, relations, mesures DAX, maquette des pages |
| Captures d'écran pour le rapport | ❌ | Liste des captures à faire (§5) |
| **Rédiger le rapport** | ✅ brouillon par chapitre | À relire, personnaliser et mettre en forme (Word / LaTeX) par vous |
| **Slides** de présentation | ✅ plan + texte (+ .pptx possible) | Vous ajoutez captures et charte |
| Slides **stage / alternance** | ❌ (votre expérience personnelle) | Gabarit 3 slides : contexte – missions – apports |
| Enregistrer la **vidéo** | ❌ | Script minuté (§7) |
| Oral / répétition | ❌ | Questions probables du jury + réponses |
| Board Jira / Trello | ❌ | Backlog prêt à copier (epics du Livrable 1 §19.1) |

---

## 5. Plan du rapport (consigne) ↔ contenu disponible

| Chapitre | Contenu | Source dans le projet | Captures à faire |
|---|---|---|---|
| **Introduction** | Contexte, problématique, objectifs, périmètre, organisation du trinôme, méthode Agile | Livrable 1 §1-8 | Schéma d'architecture |
| **Stocker** | Collecte (API + scraping éthique), ingestion Kafka, Data Lake MinIO (raw / processed / quarantine / gold), MongoDB (modèle, index, historisation), Docker | `docs/01` → `docs/05`, `docs/07`, `docs/13` | Console MinIO, Kafka UI, Compass |
| **Analyser** | Spark ETL, nettoyage, NLP compétences, salaires, géo, Data Quality (5 dimensions), dédup, KPIs Spark SQL, Airflow | `docs/04`, `docs/05`, `docs/06` | Graphe du DAG Airflow, rapport qualité |
| **Visualiser** | Application React (6 pages), Power BI (modèle en étoile, DAX) | `docs/09`, `docs/10`, `docs/11` | Chaque page du front + Power BI |
| **Sécurité** | Authentification JWT, bcrypt, RBAC, rate limiting, audit, en-têtes HTTP, réseau Docker, moindre privilège, secrets, RGPD (minimisation, PII masquées, CV non stocké), conformité CGU des sources | `docs/12` | Page login, Swagger 401/403, journal d'audit |
| **IA** | ML : classification secteur (3 algos comparés), régression salaire, clustering K-Means ; DL : Transformer multilingue (recherche sémantique, matching CV), MLP PyTorch vs TF-IDF ; métriques et limites | `docs/08` | Page IA (matching CV, métriques) |
| **Conclusion** | Apports, compétences Data Engineering maîtrisées, limites, perspectives (streaming, cluster Spark, géocodage, CI/CD, cloud) | `docs/00` §Perspectives | – |

---

### ✅ Livrables générés (dossier `deliverables/`)
- `Rapport_PFE_JobCompass.pdf` + `.docx` (éditable) – 27 pages, chiffres réels
- `Presentation_PFE_JobCompass.pptx` – 23 diapositives avec notes d'oral
- Régénérer avec les derniers chiffres (plateforme lancée) :
  ```powershell
  D:\DSP\.venvs\jobinsight\Scripts\python deliverables\collect_stats.py
  D:\DSP\.venvs\jobinsight\Scripts\python deliverables\build_report.py
  D:\DSP\.venvs\jobinsight\Scripts\python deliverables\build_slides.py
  ```
  ⚠️ Régénérer **écrase** les fichiers : faites vos retouches manuelles dans `rapport.md`
  (ou sur une copie renommée du .docx / .pptx).

## 6. Présentation (≈ 15 slides + 2-3 stage)
1. Titre · 2. Contexte & problématique · 3. Objectifs · 4. Architecture · 5. Collecte & ingestion ·
6. Data Lake & stockage · 7. Traitement Spark & Data Quality · 8. Déduplication (avant/après) ·
9. Orchestration Airflow · 10. Dashboard React · 11. Power BI · 12. IA (ML) · 13. IA (DL / matching CV) ·
14. Sécurité · 15. Bilan, difficultés, perspectives · **16-18. Stage / alternance** (contexte, missions, apports).

## 7. Script de la simulation vidéo (≈ 6-8 min)
| Temps | Écran | Message |
|---|---|---|
| 0:00 | Schéma d'architecture | Problématique et pipeline en une phrase |
| 0:45 | `docker compose ps` | Toute la plateforme conteneurisée |
| 1:15 | Airflow : déclencher `jobinsight_pipeline`, graphe des tâches | Orchestration, parallélisme, retries |
| 2:15 | Kafka UI (topic `jobs.raw`) puis MinIO (`raw/` → `processed/` → `gold/`) | Ingestion et zones du Data Lake |
| 3:00 | Logs Spark + page « Pipeline & qualité » | Nettoyage, quarantaine, doublons supprimés |
| 3:45 | Login (erreur puis succès), dashboard filtré France / 30 jours | Sécurité + KPIs |
| 4:45 | Offres (recherche, détail, lien source), Compétences | Exploration |
| 5:30 | IA : matching CV, recherche sémantique, salaire | ML / DL |
| 6:30 | Power BI | Reporting analyste |
| 7:15 | Conclusion | Apports |

---

## 8. Definition of Done (rappel Livrable 1 §21)
- [x] Développement réalisé · [x] Code testé (46 tests unitaires) · [x] Erreurs principales gérées
- [x] Documentation · [ ] Code intégré dans Git (GitLab) · [ ] Merge Request revue
- [ ] Fonctionnalité opérationnelle **vérifiée dans Docker** (bloqué par le disque C:)
