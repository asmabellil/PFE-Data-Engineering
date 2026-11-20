"""Périmètre Tech/Data : étiquette `tech_scope` posée sur chaque offre de l'entrepôt.

Pourquoi une étiquette et pas une suppression : certaines sources (WTTJ, Arbeitnow, Jobicy) publient
tous les métiers. Les offres hors périmètre restent en base (traçabilité, chiffres pour le rapport),
et l'application les masque par défaut grâce au filtre « Tech/Data seulement ».

Règle : une offre est Tech/Data si son intitulé l'indique (is_tech_title) ou si sa famille de métier,
déduite de la description ou prédite par le modèle ML, est technique.
"""
from __future__ import annotations

from pymongo import UpdateMany

from jobinsight.collectors.wttj_sitemap import is_tech_title

TECH_FAMILIES = {"Développement logiciel", "Data & IA", "DevOps & Cloud", "Cybersécurité"}


def is_tech_offer(title: str | None, industry: str | None) -> bool:
    return is_tech_title(title or "") or industry in TECH_FAMILIES


def tag_scope(db) -> dict:
    """Recalcule l'étiquette sur toute la base (après la prédiction ML des familles de métiers)."""
    ids = {True: [], False: []}
    for doc in db.jobs.find({}, {"title": 1, "industry": 1, "tech_scope": 1}):
        flag = is_tech_offer(doc.get("title"), doc.get("industry"))
        if doc.get("tech_scope") is not flag:
            ids[flag].append(doc["_id"])
    ops = [UpdateMany({"_id": {"$in": chunk}}, {"$set": {"tech_scope": flag}})
           for flag, all_ids in ids.items() for chunk in (all_ids[i:i + 1000] for i in range(0, len(all_ids), 1000))]
    if ops:
        db.jobs.bulk_write(ops, ordered=False)
    db.jobs.create_index("tech_scope")
    total = db.jobs.estimated_document_count()
    in_scope = db.jobs.count_documents({"tech_scope": True})
    return {"total": total, "tech_scope": in_scope, "out_of_scope": total - in_scope,
            "changed": len(ids[True]) + len(ids[False])}
