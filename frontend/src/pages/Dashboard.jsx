import { useState } from "react";
import { useApi, useFilters } from "../context";
import { fmtInt, label } from "../api";
import { ChartCard, Donut, HBar, State, TimeArea } from "../components/charts";
import JobDrawer from "../components/JobDrawer";

function Kpi({ icon, title, value, sub }) {
  return (
    <div className="card kpi">
      <div className="icon" aria-hidden>{icon}</div>
      <div>
        <div className="muted small">{title}</div>
        <div className="value">{value}</div>
        {sub}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { filters } = useFilters();
  const [gran, setGran] = useState("day");
  const [open, setOpen] = useState(null);
  const ov = useApi("/analytics/overview", filters);
  const tl = useApi("/analytics/timeline", { ...filters, granularity: gran });
  const ind = useApi("/analytics/breakdown/industry", filters);
  const tech = useApi("/analytics/top-technologies", { ...filters, limit: 10 });
  const ctry = useApi("/analytics/breakdown/country", { ...filters, limit: 10 });
  const latest = useApi("/jobs", { ...filters, page_size: 6 });
  const o = ov.data;
  const trend = o?.trend_pct;

  return (
    <>
      <h1>Bonjour 👋</h1>
      <p className="muted" style={{ marginTop: 0 }}>Explorez les tendances du marché de l'emploi grâce à la donnée.</p>
      <State loading={ov.loading} error={ov.error} empty={o && !o.total_total} />

      <div className="grid kpis" style={{ marginBottom: 16 }}>
        <Kpi icon="💼" title="Offres collectées" value={fmtInt(o?.total_total)}
          sub={trend !== null && trend !== undefined && (
            <div className={`delta ${trend >= 0 ? "up" : "down"}`}>{trend >= 0 ? "↗" : "↘"} {trend} % <span className="muted">30 j vs 30 j précédents</span></div>)} />
        <Kpi icon="🏢" title="Entreprises uniques" value={fmtInt(o?.companies)} />
        <Kpi icon="🧩" title="Technologies extraites" value={fmtInt(o?.technologies)} sub={<div className="muted small">+ {fmtInt(o?.skills)} compétences</div>} />
        <Kpi icon="📍" title="Pays couverts" value={fmtInt(o?.countries)} sub={<div className="muted small">{o?.remote_pct ?? 0} % en télétravail</div>} />
      </div>

      <div className="grid g3" style={{ marginBottom: 16 }}>
        <section className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h2>Évolution des offres d'emploi</h2>
            <select value={gran} onChange={(e) => setGran(e.target.value)} aria-label="Granularité">
              <option value="day">Par jour</option><option value="week">Par semaine</option><option value="month">Par mois</option>
            </select>
          </div>
          <div style={{ height: 260 }}>
            <State loading={tl.loading} error={tl.error} empty={tl.data && !tl.data.length} />
            {tl.data?.length > 0 && <TimeArea data={tl.data} />}
          </div>
        </section>
        <ChartCard title="Répartition par secteur" height={260}>
          {ind.data?.length > 0 && <Donut data={ind.data} total={o?.total_total} />}
        </ChartCard>
      </div>

      <div className="grid g2" style={{ marginBottom: 16 }}>
        <ChartCard title="Top technologies" subtitle="Nombre d'offres citant la technologie" height={320}>
          {tech.data && <HBar data={tech.data} />}
        </ChartCard>
        <ChartCard title="Répartition des offres par pays" subtitle="Top 10 (hors offres sans pays identifié)" height={320}>
          {ctry.data && <HBar data={ctry.data.filter((d) => d.label !== "unknown")} />}
        </ChartCard>
      </div>

      <section className="card">
        <h2>Dernières offres collectées</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Titre du poste</th><th>Entreprise</th><th>Localisation</th><th>Source</th><th>Date</th></tr></thead>
            <tbody>
              {latest.data?.items.map((j) => (
                <tr key={j.dedup_key} className="clickable" onClick={() => setOpen(j.dedup_key)}>
                  <td><b>{j.title}</b></td><td>{j.company}</td>
                  <td>{[j.city, j.country].filter(Boolean).join(", ") || (j.remote ? "Télétravail" : "–")}</td>
                  <td>{(j.sources || [j.source]).map((s) => <span key={s} className="tag">{label(s)}</span>)}</td>
                  <td>{j.publication_date ? new Date(j.publication_date).toLocaleDateString("fr-FR") : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {open && <JobDrawer id={open} onClose={() => setOpen(null)} />}
    </>
  );
}
