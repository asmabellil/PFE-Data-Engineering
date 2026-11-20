"""Dédoublonnage par similarité (MinHash LSH, Spark MLlib), après le dédoublonnage exact.

Le dédoublonnage exact fusionne deux offres seulement si entreprise, titre et ville normalisés sont
identiques. Une même offre republiée par un agrégateur passe donc à travers dès qu'un mot change
(« Data Engineer H/F - Paris » contre « Data Engineer confirmé Paris 9e »).

Méthode, en deux temps pour rester rapide et précise :
1. Candidats : MinHash LSH estime la similarité de Jaccard entre les ensembles de mots (titre) et de
   paires de mots (début de description). Seules les paires à moins de JACCARD_MAX_DISTANCE sont
   comparées : on évite la comparaison de toutes les offres deux à deux.
2. Confirmation par règles métier : sources différentes (une même source publie des postes distincts,
   souvent avec le même texte de présentation de l'employeur), même entreprise, même ville (ou ville
   inconnue), publication à moins de MAX_DAYS_APART jours d'écart, puis :
   - descriptions des deux côtés : descriptions très proches ET titres proches ;
   - sinon : titres identiques (aux marqueurs de genre près). Une première version qui acceptait
     des titres seulement « proches » fusionnait des postes différents d'un même employeur
     (stage et CDI, régions différentes) : la règle a été durcie après lecture des résultats réels.
   Les doublons confirmés sont regroupés (union-find) et seule l'offre la plus complète est gardée,
   avec la liste fusionnée des sources.

Limite assumée : la comparaison se fait à l'intérieur d'un lot (chaque run recollecte des fenêtres
qui se recouvrent, donc les republications d'une même période se retrouvent dans le même lot).
"""
from __future__ import annotations

from datetime import date

from jobinsight.processing.cleaning import norm_company_key, norm_key

JACCARD_MAX_DISTANCE = 0.3   # au moins 70 % de mots en commun pour devenir candidat
MAX_DAYS_APART = 10
TITLE_MIN_SIMILARITY = 0.65        # titres proches (avec descriptions des deux côtés) ; 0.5 fusionnait deux régions
DESCRIPTION_MIN_SIMILARITY = 0.7   # descriptions très proches : c'est elles qui prouvent le doublon
DESCRIPTION_CHARS = 1500
# Seuls les marqueurs de genre et CDI/CDD sont ignorés. « Stage », « alternance », une région ou une
# spécialité distinguent bien deux offres d'un même employeur (constaté sur les données réelles).
_NOISE = {"h", "f", "m", "w", "d", "x", "hf", "fh", "cdi", "cdd"}


def title_tokens(title: str | None) -> set[str]:
    return {w for w in norm_key(title).split() if w not in _NOISE}


def description_bigrams(description: str | None) -> set[str]:
    words = norm_key((description or "")[:DESCRIPTION_CHARS]).split()
    return {f"{a}_{b}" for a, b in zip(words, words[1:])}


def tokens(title: str | None, description: str | None) -> list[str]:
    """Mots du titre + paires de mots consécutifs du début de la description (plus discriminantes)."""
    return sorted(title_tokens(title) | description_bigrams(description))


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a or b else 0.0


def _days_apart(a: str | None, b: str | None) -> int | None:
    try:
        return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)
    except (TypeError, ValueError):
        return None


def confirm(a: dict, b: dict) -> bool:
    """Règles métier qui confirment qu'une paire candidate est bien la même offre."""
    # Une source ne republie pas deux fois la même offre (son identifiant l'en empêche, et le
    # dédoublonnage exact s'en charge) : deux offres proches d'une même source sont des postes
    # distincts (autre rôle, autre pays). Seules les republications entre sources sont fusionnées.
    if set(a.get("sources") or []) & set(b.get("sources") or []):
        return False
    company = norm_company_key(a.get("company"))
    if not company or company != norm_company_key(b.get("company")):
        return False
    city_a, city_b = norm_key(a.get("city")), norm_key(b.get("city"))
    if city_a and city_b and city_a != city_b:
        return False
    gap = _days_apart(a.get("publication_date"), b.get("publication_date"))
    if gap is not None and gap > MAX_DAYS_APART:
        return False
    title_a, title_b = title_tokens(a.get("title")), title_tokens(b.get("title"))
    desc_a, desc_b = description_bigrams(a.get("description")), description_bigrams(b.get("description"))
    if desc_a and desc_b:
        return jaccard(title_a, title_b) >= TITLE_MIN_SIMILARITY and jaccard(desc_a, desc_b) >= DESCRIPTION_MIN_SIMILARITY
    # sans description, le titre ne suffit pas à distinguer deux postes d'un même employeur :
    # seuls des intitulés identiques (aux marqueurs de genre près) sont considérés comme la même offre
    return bool(title_a) and title_a == title_b


def group_pairs(pairs: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Regroupe les paires en groupes de doublons (union-find) : racine -> membres."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    groups: dict[str, list[str]] = {}
    for x in parent:
        groups.setdefault(find(x), []).append(x)
    return {root: sorted(members) for root, members in groups.items() if len(members) > 1}


def fuzzy_dedup(spark, df):
    """df : une ligne par dedup_key (après dédoublonnage exact). Renvoie (df, statistiques, exemples)."""
    from pyspark.ml.feature import HashingTF, MinHashLSH
    from pyspark.sql import functions as F
    from pyspark.sql import types as T

    tok = F.udf(tokens, T.ArrayType(T.StringType()))
    feats = (df.select("dedup_key", "title", "description").withColumn("tokens", tok("title", "description"))
             .filter(F.size("tokens") > 0))
    vec = HashingTF(inputCol="tokens", outputCol="features", numFeatures=1 << 18, binary=True).transform(feats)
    model = MinHashLSH(inputCol="features", outputCol="hashes", numHashTables=5, seed=42).fit(vec)
    candidates = (
        model.approxSimilarityJoin(vec, vec, JACCARD_MAX_DISTANCE, distCol="distance")
        .filter(F.col("datasetA.dedup_key") < F.col("datasetB.dedup_key"))
        .select(F.col("datasetA.dedup_key").alias("a"), F.col("datasetB.dedup_key").alias("b"))
        .collect()
    )
    stats = {"fuzzy_candidates": len(candidates), "fuzzy_confirmed_pairs": 0, "fuzzy_duplicates_removed": 0}
    if not candidates:
        return df, stats, []

    keys = sorted({c["a"] for c in candidates} | {c["b"] for c in candidates})
    cols = ["dedup_key", "title", "company", "city", "publication_date", "description", "completeness",
            "collected_at", "sources"]
    info = {r["dedup_key"]: r.asDict() for r in df.filter(F.col("dedup_key").isin(keys)).select(*cols).collect()}
    confirmed = [(c["a"], c["b"]) for c in candidates if confirm(info[c["a"]], info[c["b"]])]
    groups = group_pairs(confirmed)

    drop: set[str] = set()
    merged: dict[str, list[str]] = {}
    examples = []
    for members in groups.values():
        best = max(members, key=lambda k: (info[k]["completeness"] or 0, info[k]["collected_at"] or ""))
        merged[best] = sorted({s for k in members for s in (info[k]["sources"] or [])})
        drop.update(m for m in members if m != best)
        if len(examples) < 10:
            examples.append({"kept": info[best]["title"], "company": info[best]["company"],
                             "merged": [info[m]["title"] for m in members if m != best], "sources": merged[best]})
    stats.update(fuzzy_confirmed_pairs=len(confirmed), fuzzy_duplicates_removed=len(drop))

    out = df.filter(~F.col("dedup_key").isin(sorted(drop)))
    patch = spark.createDataFrame(list(merged.items()), "dedup_key string, merged_sources array<string>")
    out = (out.join(patch, "dedup_key", "left")
           .withColumn("sources", F.coalesce(F.col("merged_sources"), F.col("sources"))).drop("merged_sources"))
    return out, stats, examples
