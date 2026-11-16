import { useState } from "react";
import { useApi, useFilters } from "../context";
import { ChartCard, HBar, MultiLine } from "../components/charts";

const SKILL_CATS = ["Technique", "Comportementale", "Langue"];

export default function Skills() {
  const { filters } = useFilters();
  const [cat, setCat] = useState("Technique");
  const tech = useApi("/analytics/top-technologies", { ...filters, limit: 25 });
  const skills = useApi("/analytics/top-skills", { ...filters, category: cat, limit: 15 });
  const top5 = tech.data?.slice(0, 5).map((t) => t.label) || [];
  const trend = useApi("/analytics/technology-trend", { ...filters, technologies: top5.join(",") }, [top5.join(",")]);

  const byCategory = {};
  tech.data?.forEach((t) => { (byCategory[t.category || "Autre"] ||= []).push(t); });

  return (
    <>
      <h1>Compétences & technologies</h1>
      <p className="muted" style={{ marginTop: 0 }}>Extraites automatiquement des descriptions par NLP (taxonomie FR / EN / DE).</p>

      <div className="grid g2" style={{ marginBottom: 16 }}>
        <ChartCard title="Technologies les plus demandées" subtitle="Top 25" height={560}>
          {tech.data && <HBar data={tech.data} />}
        </ChartCard>
        <div className="grid" style={{ alignContent: "start" }}>
          <section className="card">
            <h2>Compétences</h2>
            <div className="tabs">
              {SKILL_CATS.map((c) => <button key={c} className={c === cat ? "on" : ""} onClick={() => setCat(c)}>{c === "Comportementale" ? "Soft skills" : c === "Langue" ? "Langues" : "Techniques / métier"}</button>)}
            </div>
            <div style={{ height: 380 }}>{skills.data && <HBar data={skills.data} />}</div>
          </section>
          <section className="card">
            <h2>Technologies par catégorie</h2>
            {Object.entries(byCategory).map(([c, items]) => (
              <div key={c} style={{ marginBottom: 8 }}>
                <div className="muted small">{c}</div>
                {items.map((t) => <span key={t.label} className="tag">{t.label} · {t.jobs}</span>)}
              </div>
            ))}
          </section>
        </div>
      </div>

      <ChartCard title="Évolution quotidienne des 5 technologies les plus demandées" height={300}>
        {trend.data?.points?.length > 0 && <MultiLine data={trend.data.points} keys={trend.data.technologies} />}
      </ChartCard>
    </>
  );
}
