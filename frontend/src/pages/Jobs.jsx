import { useState } from "react";
import { useApi, useFilters } from "../context";
import { fmtEur, fmtInt, label } from "../api";
import JobDrawer from "../components/JobDrawer";
import { State } from "../components/charts";

const EMPTY = { q: "", contract_type: "", experience_level: "", industry: "", technology: "", source: "", remote: "", with_salary: "" };

export default function Jobs() {
  const { filters } = useFilters();
  const [f, setF] = useState(EMPTY);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("recent");
  const [open, setOpen] = useState(null);
  const opts = useApi("/jobs/filters").data;
  const { data, loading, error } = useApi("/jobs", { ...filters, ...f, page, sort, page_size: 20 });
  const set = (k) => (e) => { setF({ ...f, [k]: e.target.value }); setPage(1); };
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  const sel = (k, values, placeholder) => (
    <select value={f[k]} onChange={set(k)} aria-label={placeholder}>
      <option value="">{placeholder}</option>
      {values?.map((v) => <option key={v} value={v}>{label(v)}</option>)}
    </select>
  );

  return (
    <>
      <h1>Offres d'emploi</h1>
      <p className="muted" style={{ marginTop: 0 }}>{data ? `${fmtInt(data.total)} offres correspondantes` : " "}</p>
      <section className="card">
        <form className="toolbar" onSubmit={(e) => { e.preventDefault(); setF({ ...f, q }); setPage(1); }}>
          <input placeholder="Rechercher (poste, entreprise, mot-clé)…" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: "1 1 260px" }} maxLength={100} />
          <button>Rechercher</button>
          {sel("contract_type", opts?.contract_type, "Contrat")}
          {sel("experience_level", opts?.experience_level, "Expérience")}
          {sel("industry", opts?.industry, "Secteur")}
          {sel("technology", opts?.technologies, "Technologie")}
          {sel("source", opts?.sources, "Source")}
          <select value={f.remote} onChange={set("remote")} aria-label="Télétravail">
            <option value="">Télétravail ?</option><option value="true">Oui</option><option value="false">Non</option>
          </select>
          <select value={f.with_salary} onChange={set("with_salary")} aria-label="Salaire">
            <option value="">Salaire ?</option><option value="true">Avec salaire</option>
          </select>
          <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Tri">
            <option value="recent">Plus récentes</option><option value="salary">Salaire le plus haut</option><option value="company">Entreprise A→Z</option>
          </select>
          <button type="button" className="ghost" onClick={() => { setF(EMPTY); setQ(""); setPage(1); }}>Réinitialiser</button>
        </form>
        <State loading={loading} error={error} empty={data && !data.total} />
        {data?.items?.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Poste</th><th>Entreprise</th><th>Localisation</th><th>Contrat</th><th>Niveau</th><th>Salaire / an</th><th>Technologies</th><th>Date</th></tr></thead>
              <tbody>
                {data.items.map((j) => (
                  <tr key={j.dedup_key} className="clickable" onClick={() => setOpen(j.dedup_key)}>
                    <td><b>{j.title}</b><div className="muted small">{(j.sources || [j.source]).map(label).join(" · ")}</div></td>
                    <td>{j.company}</td>
                    <td>{[j.city, j.country].filter(Boolean).join(", ") || "–"}{j.remote && <div className="small muted">Télétravail</div>}</td>
                    <td>{j.contract_type ? label(j.contract_type) : "–"}</td>
                    <td>{j.experience_level ? label(j.experience_level) : "–"}</td>
                    <td>{j.salary_annual_min_eur ? `${fmtEur(j.salary_annual_min_eur)} – ${fmtEur(j.salary_annual_max_eur)}` : "–"}</td>
                    <td>{j.technologies?.slice(0, 4).map((t) => <span key={t} className="tag">{t}</span>)}</td>
                    <td>{j.publication_date || "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="pager">
          <button className="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Précédent</button>
          <span className="muted small">Page {page} / {pages}</span>
          <button className="ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>Suivant →</button>
        </div>
      </section>
      {open && <JobDrawer id={open} onClose={() => setOpen(null)} />}
    </>
  );
}
