"""Job Spark – Analyse & KPIs (couche Gold) + exports Power BI.

Lit TOUTE la zone processed/ du Data Lake (historique complet), garde la version la plus
récente de chaque offre, puis calcule les indicateurs du Livrable 1 §14 :
volume, localisation, technologies, compétences, expérience, contrats, salaires.

Sorties :
- gold/<kpi>/<run_id>/*.parquet       dans le Data Lake
- EXPORTS_DIR/*.csv                   modèle en étoile pour Power BI
- MongoDB.kpi_snapshots               historique des KPIs globaux
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from jobinsight.config import Settings, get_settings
from jobinsight.lake import DataLake
from jobinsight.processing.skills import SKILLS, TECHNOLOGIES
from jobinsight.processing.spark_etl import get_spark
from jobinsight.utils import get_logger

log = get_logger("spark.analytics")


def _write_csv(df, path: Path) -> None:
    """Écrit un unique CSV (UTF-8 avec BOM pour Excel / Power BI)."""
    pdf = df.toPandas()
    for col in pdf.columns:
        if pdf[col].dtype == object:
            pdf[col] = pdf[col].apply(lambda v: "|".join(v) if isinstance(v, (list, tuple)) else v)
    pdf.to_csv(path, index=False, encoding="utf-8-sig")


def run_analytics(run_id: str, settings: Settings | None = None) -> dict:
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    settings = settings or get_settings()
    lake = DataLake(settings)
    work = Path(tempfile.mkdtemp(prefix=f"gold_{run_id}_"))
    exports = Path(settings.exports_dir)
    exports.mkdir(parents=True, exist_ok=True)
    try:
        files = lake.download_prefix("processed/jobs/", work / "in", suffix=".parquet")
        if not files:
            return {"run_id": run_id, "status": "no_data"}
        spark = get_spark("jobinsight-analytics")
        raw = spark.read.parquet(*files)

        from jobinsight.warehouse.mongo_loader import get_db

        # secteurs prédits par le modèle ML (offres sans secteur fourni par la source)
        preds = [(d["dedup_key"], d["industry"]) for d in get_db(settings).jobs.find(
            {"industry_source": "ml"}, {"dedup_key": 1, "industry": 1, "_id": 0})]
        pred_df = spark.createDataFrame(preds or [("__none__", None)],
                                        "dedup_key string, industry_ml string")

        w = Window.partitionBy("dedup_key").orderBy(F.desc("collected_at"))
        jobs = (raw.withColumn("_rn", F.row_number().over(w)).filter("_rn = 1").drop("_rn")
                .join(pred_df, "dedup_key", "left")
                .withColumn("industry_source", F.when(F.col("industry").isNull() & F.col("industry_ml").isNotNull(),
                                                      F.lit("ml")).otherwise(F.col("industry_source")))
                .withColumn("industry", F.coalesce("industry", "industry_ml")).drop("industry_ml")
                .withColumn("salary_mid_eur",
                            (F.col("salary_annual_min_eur") + F.col("salary_annual_max_eur")) / 2)
                .withColumn("pub_month", F.substring("publication_date", 1, 7))
                .cache())
        jobs.createOrReplaceTempView("jobs")
        n_jobs = jobs.count()

        tech = jobs.select("job_id", "dedup_key", F.explode("technologies").alias("technology"))
        skill = jobs.select("job_id", "dedup_key", F.explode("skills").alias("skill"))
        tech.createOrReplaceTempView("job_tech")
        skill.createOrReplaceTempView("job_skill")
        spark.createDataFrame([(k, v[0]) for k, v in TECHNOLOGIES.items()],
                              "technology string, tech_category string").createOrReplaceTempView("dim_tech")
        spark.createDataFrame([(k, v[0]) for k, v in SKILLS.items()],
                              "skill string, skill_category string").createOrReplaceTempView("dim_skill")

        q = spark.sql
        kpis = {
            "jobs_by_day": q("""SELECT publication_date AS day, COUNT(*) AS jobs FROM jobs
                                WHERE publication_date IS NOT NULL GROUP BY 1 ORDER BY 1"""),
            "top_technologies": q("""SELECT t.technology, d.tech_category, COUNT(DISTINCT t.dedup_key) AS jobs,
                                     ROUND(100 * COUNT(DISTINCT t.dedup_key) / {n}, 2) AS pct_jobs
                                     FROM job_tech t LEFT JOIN dim_tech d USING (technology)
                                     GROUP BY 1, 2 ORDER BY jobs DESC""".format(n=n_jobs)),
            "top_skills": q("""SELECT s.skill, d.skill_category, COUNT(DISTINCT s.dedup_key) AS jobs
                               FROM job_skill s LEFT JOIN dim_skill d USING (skill)
                               GROUP BY 1, 2 ORDER BY jobs DESC"""),
            "by_country": q("""SELECT COALESCE(country, 'Non renseigné') AS country, COUNT(*) AS jobs,
                               SUM(CASE WHEN remote THEN 1 ELSE 0 END) AS remote_jobs
                               FROM jobs GROUP BY 1 ORDER BY jobs DESC"""),
            "by_contract": q("""SELECT COALESCE(contract_type, 'unknown') AS contract_type, COUNT(*) AS jobs
                                FROM jobs GROUP BY 1 ORDER BY jobs DESC"""),
            "by_experience": q("""SELECT COALESCE(experience_level, 'unknown') AS experience_level,
                                  COUNT(*) AS jobs, ROUND(AVG(salary_mid_eur)) AS avg_salary_eur
                                  FROM jobs GROUP BY 1 ORDER BY jobs DESC"""),
            "by_industry": q("""SELECT COALESCE(industry, 'Non classé') AS industry, COUNT(*) AS jobs
                                FROM jobs GROUP BY 1 ORDER BY jobs DESC"""),
            "by_source": q("""SELECT source, COUNT(*) AS jobs FROM jobs GROUP BY 1 ORDER BY jobs DESC"""),
            "salary_by_experience": q("""SELECT COALESCE(experience_level, 'unknown') AS experience_level,
                    COUNT(*) AS n, ROUND(MIN(salary_annual_min_eur)) AS min_eur,
                    ROUND(percentile_approx(salary_mid_eur, 0.5)) AS median_eur,
                    ROUND(AVG(salary_mid_eur)) AS avg_eur, ROUND(MAX(salary_annual_max_eur)) AS max_eur
                    FROM jobs WHERE salary_mid_eur IS NOT NULL GROUP BY 1 ORDER BY median_eur"""),
            "salary_by_technology": q("""SELECT t.technology, COUNT(*) AS n,
                    ROUND(percentile_approx(j.salary_mid_eur, 0.5)) AS median_eur,
                    ROUND(AVG(j.salary_mid_eur)) AS avg_eur
                    FROM job_tech t JOIN jobs j USING (dedup_key)
                    WHERE j.salary_mid_eur IS NOT NULL GROUP BY 1 HAVING n >= 3 ORDER BY median_eur DESC"""),
            "technology_trend": q("""SELECT j.pub_month AS month, t.technology, COUNT(*) AS jobs
                    FROM job_tech t JOIN jobs j USING (dedup_key) WHERE j.pub_month IS NOT NULL
                    GROUP BY 1, 2 ORDER BY 1, 3 DESC"""),
        }

        gold_dir = work / "gold"
        for name, df in kpis.items():
            df.coalesce(1).write.mode("overwrite").parquet(str(gold_dir / name))
            _write_csv(df, exports / f"kpi_{name}.csv")
        lake.upload_dir(gold_dir, f"gold/{run_id}", suffixes=(".parquet",))

        # ---------------- Modèle en étoile pour Power BI ----------------
        fact_cols = ["job_id", "dedup_key", "title", "company", "city", "country", "region", "remote",
                     "contract_type", "experience_level", "years_experience", "industry",
                     "industry_source", "salary_annual_min_eur", "salary_annual_max_eur",
                     "salary_mid_eur", "currency", "publication_date", "pub_month", "source",
                     "sources", "completeness", "url"]
        _write_csv(jobs.select(*fact_cols), exports / "fact_jobs.csv")
        _write_csv(tech, exports / "bridge_job_technology.csv")
        _write_csv(skill, exports / "bridge_job_skill.csv")
        _write_csv(q("SELECT * FROM dim_tech"), exports / "dim_technology.csv")
        _write_csv(q("SELECT * FROM dim_skill"), exports / "dim_skill.csv")

        overview_row = q("""SELECT COUNT(*) AS total_jobs, COUNT(DISTINCT company) AS companies,
                    COUNT(DISTINCT country) AS countries, COUNT(DISTINCT source) AS sources,
                    SUM(CASE WHEN remote THEN 1 ELSE 0 END) AS remote_jobs,
                    SUM(CASE WHEN salary_mid_eur IS NOT NULL THEN 1 ELSE 0 END) AS jobs_with_salary,
                    ROUND(percentile_approx(salary_mid_eur, 0.5)) AS median_salary_eur
                    FROM jobs""").first().asDict()
        overview_row["technologies"] = tech.select("technology").distinct().count()
        overview_row["skills"] = skill.select("skill").distinct().count()
        overview = {"run_id": run_id, "created_at": datetime.now(timezone.utc), **overview_row}
        get_db(settings).kpi_snapshots.insert_one(dict(overview))
        overview["created_at"] = overview["created_at"].isoformat()
        overview.pop("_id", None)
        log.info("KPIs : %s", overview)
        return {"run_id": run_id, "status": "success", "overview": overview,
                "exports": sorted(p.name for p in exports.glob("*.csv"))}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    print(json.dumps(run_analytics(args.run_id), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
