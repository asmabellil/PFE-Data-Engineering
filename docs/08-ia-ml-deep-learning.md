# 08 – Intelligence artificielle : Machine Learning et Deep Learning

**Outils** : scikit-learn 1.5 (TF-IDF, Logistic Regression, Linear SVM, Naive Bayes, Ridge,
Random Forest, TruncatedSVD, K-Means), **Sentence-Transformers** (Transformer multilingue),
**PyTorch** 2.5 (réseau de neurones), joblib
**Code** : `pipeline/jobinsight/ml/` (ML, entraîné par Airflow) · `backend/app/ai/` (DL, servi par l'API)

## Vue d'ensemble

| # | Tâche | Type | Modèle | Usage dans la plateforme |
|---|---|---|---|---|
| 1 | Secteur d'une offre | Classification supervisée (NLP) | TF-IDF + 3 algos comparés | **enrichit** les offres sans secteur (Arbeitnow…) |
| 2 | Salaire annuel | Régression | Ridge vs Random Forest vs baseline | estimation dans la page IA |
| 3 | Familles de métiers | Clustering non supervisé | TF-IDF → SVD (LSA) → K-Means | exploration, `cluster_id` |
| 4 | Recherche sémantique | Deep Learning (Transformer) | paraphrase-multilingual-MiniLM-L12-v2 | moteur de recherche « par le sens » |
| 5 | Matching CV ↔ offres | DL + règles | embeddings + recouvrement des technologies | recommandations + compétences à acquérir |
| 6 | Secteur (version DL) | Deep Learning (MLP) | réseau 384-256-128-n sur embeddings | comparaison ML vs DL |

## 1. Classification du secteur (ML)
- **Données** : offres dont la source fournit le secteur (Jobicy, Remotive, python.org…), classes
  avec ≥ 8 exemples ; split stratifié 80/20.
- **Texte** : titre (×2) + tags + technologies + 1 500 premiers caractères de la description.
- **Vectorisation** : TF-IDF unigrammes + bigrammes, `sublinear_tf`, accents retirés.
- **Algorithmes comparés** (métrique principale : **macro-F1**, adaptée aux classes déséquilibrées) :
  Logistic Regression (`class_weight=balanced`), Linear SVM calibré, Complement Naive Bayes.
- Le meilleur est ré-entraîné sur 100 % des données puis **prédit le secteur manquant** (seuil de
  confiance 0,35) → `industry_source = "ml"`, `industry_confidence`.

## 2. Estimation du salaire (ML)
- **Cible** : log(salaire annuel médian en EUR) – le log stabilise la variance.
- **Variables** : titre (TF-IDF), technologies (multi-hot), expérience, pays, contrat, télétravail,
  secteur (one-hot) – `ColumnTransformer`.
- **Comparaison** : baseline (médiane), Ridge, Random Forest – métriques MAE (€) et R².
- Premier essai (68 offres, 16/11) : baseline MAE 50,5 k€ ; Ridge 59,1 k€ ; **Random Forest 46,4 k€ (R² 0,24)**.
  → modèle **indicatif** : peu d'offres publient un salaire (risque identifié dans le Livrable 1) ;
  les performances s'améliorent avec l'accumulation de données. L'API renvoie toujours un
  intervalle ± MAE.

## 3. Clustering des métiers (ML non supervisé)
TF-IDF (titre + technologies, mots vides EN/FR/DE et niveaux retirés) → **TruncatedSVD 100 dim**
(analyse sémantique latente) → normalisation L2 → **K-Means**, k ∈ [6, 14] choisi par le
**score de silhouette**. Chaque cluster est décrit par ses termes, technologies et secteurs dominants.
Exemple réel : « Python / Engineer / ML », « AWS / Azure / AI », « JavaScript / Java / Developer »,
« CI / CD / Engineer », « Customer / Success », « Account / Executive / Enterprise »…

## 4. Recherche sémantique (Deep Learning)
- Modèle **Sentence-Transformer** pré-entraîné `paraphrase-multilingual-MiniLM-L12-v2` :
  Transformer de type BERT distillé, 12 couches, embeddings de **384 dimensions**, 50+ langues.
- Chaque offre → vecteur (titre + technologies + description) stocké dans `job_embeddings`.
- Requête → vecteur → **similarité cosinus** (produit scalaire de vecteurs normalisés, NumPy).
- Intérêt : « ingénieur données » trouve « Data Engineer » et « Dateningenieur » (multilingue),
  impossible avec une recherche par mots-clés.
- Indexation incrémentale déclenchée par Airflow après chaque run (`/api/ai/reindex`).

## 5. Matching CV ↔ offres
`score = 0,7 × similarité sémantique + 0,3 × part des technologies de l'offre présentes dans le CV`.
Retourne pour chaque offre les technologies **maîtrisées** / **manquantes** et un classement des
compétences à acquérir. Le CV est traité **en mémoire, jamais stocké** (RGPD).

## 6. Réseau de neurones PyTorch (Deep Learning)
**Transfer learning** : le Transformer (gelé) sert d'extracteur de caractéristiques, un MLP est entraîné :
```
Linear(384,256) → ReLU → Dropout(0.3) → Linear(256,128) → ReLU → Dropout(0.3) → Linear(128,n)
```
Adam (lr 1e-3, weight decay 1e-4), entropie croisée **pondérée** (classes déséquilibrées),
mini-batchs de 64, **early stopping** sur la macro-F1 de validation (patience 8).
Les métriques sont enregistrées à côté de celles du meilleur modèle TF-IDF → tableau
**ML vs DL** pour le rapport (page IA → Modèles). Lancement : `POST /api/ai/train-dl` ou DAG `jobinsight_ml`.

## Suivi des expériences
Chaque entraînement est historisé dans `ml_runs` (modèle, métriques, comparaison, date) et
affiché dans le front. Les modèles sont sauvegardés dans `models/` (joblib / .pt).

## Points de discussion pour le rapport
- Données de labels « faibles » (secteur fourni par la source, parfois large) ;
- déséquilibre des classes → macro-F1 et pondération ;
- peu de salaires → régression indicative ;
- DL plus coûteux mais multilingue et sémantique ; TF-IDF rapide et explicable.
