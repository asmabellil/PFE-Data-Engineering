import { useEffect, useRef, useState } from "react";
import { useApi, useAuth, useFilters } from "../context";
import { fmtInt, label } from "../api";
import { categoryKey, ChartCard, colorFor, Donut, HBar, Skeleton, StackedArea, State } from "../components/charts";
import Icon from "../components/Icon";
import JobDrawer from "../components/JobDrawer";

// Signal ponctuel : la valeur grossit brièvement quand elle change (ex. après un changement de filtre)
function usePulse(value, ready) {
  const [pulse, setPulse] = useState(false);
  const previous = useRef(value);
  useEffect(() => {
    if (!ready || previous.current === value) return undefined;
    const first = previous.current === undefined || previous.current === "0";
    previous.current = value;
    if (first) return undefined;
    setPulse(true);
    const timer = setTimeout(() => setPulse(false), 240);
    return () => clearTimeout(timer);
  }, [value, ready]);
  return pulse;
}

function Kpi({ icon, color, title, value, sub, loading }) {
  const pulse = usePulse(value, !loading);
  return (
    <div className="card kpi">
      <div className={`kpi-icon ${color}`} aria-hidden><Icon name={icon} size={20} /></div>
      <div style={{ minWidth: 0 }}>
        <div className="stat-label">{title}</div>
        {loading ? <Skeleton height={28} label={`Chargement : ${title}`} /> : <div className={`stat-value${pulse ? " pulse" : ""}`}>{value}</div>}
        {!loading && sub}
      </div>
    </div>
  );
}

const DEFAULT_WINDOW = {
  day: { days: 30, text: "30 derniers jours" },
  week: { days: 182, text: "6 derniers mois" },
  month: { days: null, text: "tout l'historique" },
};

export default function Dashboard() {
  const { user } = useAuth();
  const { filters } = useFilters();
  const [gran, setGran] = useState("day");
  const [open, setOpen] = useState(null);
  const ov = useApi("/analytics/overview", filters);
  // Fenêtre par défaut de la courbe : quelques vieilles offres étiraient l'axe et laissaient 90 % du graphique vide.
  // Le filtre « période » de la barre du haut reste prioritaire.
  const windowDays = filters.days || DEFAULT_WINDOW[gran].days;
  const tl = useApi("/analytics/timeline", { ...filters, days: windowDays || undefined, granularity: gran, by: "source" });
  const ind = useApi("/analytics/breakdown/industry", filters);
  const tech = useApi("/analytics/top-technologies", { ...filters, limit: 10 });
  const ctry = useApi("/analytics/breakdown/country", { ...filters, limit: 10 });
  const latest = useApi("/jobs", { ...filters, page_size: 6 });
  const o = ov.data;
  const trend = o?.trend_pct;
  const firstName = (user.full_name || "").split(" ")[0];

  return (
    <>
      <div className="page-head">
        <h1>Bonjour{firstName ? ` ${firstName}` : ""}</h1>
        <p>Explorez les tendances du marché de l'emploi grâce à la donnée.</p>
      </div>
      {!ov.loading && <State error={ov.error} empty={o && !o.total_total} />}

      <div className="grid kpis mb">
        <Kpi icon="briefcase" color="blue" title="Offres collectées" value={fmtInt(o?.total_total)} loading={ov.loading}
          sub={trend !== null && trend !== undefined && (
            <div className={`delta ${trend >= 0 ? "up" : "down"}`}>{trend >= 0 ? "↗" : "↘"} {trend} % <span className="muted">sur 30 jours</span></div>)} />
        <Kpi icon="building" color="purple" title="Entreprises uniques" value={fmtInt(o?.companies)} loading={ov.loading} />
        <Kpi icon="cpu" color="cyan" title="Technologies extraites" value={fmtInt(o?.technologies)} loading={ov.loading}
          sub={<div className="muted small">et {fmtInt(o?.skills)} compétences</div>} />
        <Kpi icon="pin" color="orange" title="Pays couverts" value={fmtInt(o?.countries)} loading={ov.loading}
          sub={<div className="muted small">{o?.remote_pct ?? 0} % en télétravail</div>} />
      </div>

      <div className="grid g3 mb">
        <section className="card">
          <div className="card-title">
            <Icon name="trending" size={20} />
            <h2>Évolution des offres d'emploi</h2>
            <span className="spacer" />
            <select value={gran} onChange={(e) => setGran(e.target.value)} aria-label="Granularité">
              <option value="day">Par jour</option><option value="week">Par semaine</option><option value="month">Par mois</option>
            </select>
          </div>
          <div className="card-sub">
            Par source de données, {filters.days ? `${filters.days} derniers jours (filtre de période)` : DEFAULT_WINDOW[gran].text}
          </div>
          <div style={{ height: 280 }} aria-busy={tl.loading || undefined}>
            {tl.loading ? <Skeleton height={280} label="Chargement de l'évolution des offres" />
              : <>
                <State error={tl.error} empty={tl.data && !tl.data.rows?.length} />
                {tl.data?.rows?.length > 0 && <StackedArea data={tl.data.rows} keys={tl.data.keys} totals={tl.data.totals} />}
              </>}
          </div>
        </section>
        <ChartCard title="Répartition par secteur" icon="layers" height={260} loading={ind.loading}>
          {ind.data?.length > 0 && <Donut data={ind.data} total={o?.total_total} dimension="industry" />}
        </ChartCard>
      </div>

      <div className="grid g2 mb">
        <ChartCard title="Top technologies" icon="cpu" subtitle="Nombre d'offres citant la technologie, couleur par catégorie" height={340} loading={tech.loading}>
          {tech.data && <HBar data={tech.data} colorOf={(r, i) => colorFor("techCategory", r.category, i)}
            keyItems={categoryKey(tech.data, "category", "techCategory")} />}
        </ChartCard>
        <ChartCard title="Répartition des offres par pays" icon="globe" subtitle="Top 10, hors offres sans pays identifié" height={320} loading={ctry.loading}>
          {ctry.data && <HBar data={ctry.data.filter((d) => d.label !== "unknown")} />}
        </ChartCard>
      </div>

      <section className="card">
        <div className="card-title"><Icon name="briefcase" size={20} /><h2>Dernières offres collectées</h2></div>
        {latest.loading ? <Skeleton lines={5} label="Chargement des dernières offres" /> : (
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
        )}
      </section>
      {open && <JobDrawer id={open} onClose={() => setOpen(null)} />}
    </>
  );
}
