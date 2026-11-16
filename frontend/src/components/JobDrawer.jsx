import { useEffect } from "react";
import { useApi } from "../context";
import { fmtEur, label } from "../api";

export default function JobDrawer({ id, onClose }) {
  const { data: j, loading, error } = useApi(`/jobs/${id}`);
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="drawer-bg" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <button className="ghost" onClick={onClose} style={{ float: "right" }}>✕</button>
        {loading && <div className="muted">Chargement…</div>}
        {error && <div className="error">{error}</div>}
        {j && (
          <>
            <h1>{j.title}</h1>
            <p className="muted">{j.company} · {[j.city, j.country].filter(Boolean).join(", ") || j.location || "–"} {j.remote && "· 🏠 Télétravail"}</p>
            <p>
              {j.contract_type && <span className="tag">{label(j.contract_type)}</span>}
              {j.experience_level && <span className="tag">{label(j.experience_level)}</span>}
              {j.industry && <span className="tag">{j.industry}{j.industry_source === "ml" ? " (prédit par IA)" : ""}</span>}
              {j.salary_annual_min_eur && <span className="tag">💶 {fmtEur(j.salary_annual_min_eur)} – {fmtEur(j.salary_annual_max_eur)} / an</span>}
            </p>
            {j.technologies?.length > 0 && <><h2>Technologies</h2><p>{j.technologies.map((t) => <span key={t} className="tag">{t}</span>)}</p></>}
            {j.skills?.length > 0 && <><h2>Compétences</h2><p>{j.skills.map((t) => <span key={t} className="tag">{t}</span>)}</p></>}
            <h2>Description</h2>
            <div className="desc">{j.description || "Description non fournie par la source."}</div>
            <hr style={{ border: 0, borderTop: "1px solid var(--border)", margin: "18px 0" }} />
            {/* attribution obligatoire (conditions d'utilisation des API) */}
            <p className="small">
              Source : {(j.sources || [j.source]).map(label).join(", ")} · publiée le {j.publication_date || "–"} ·
              vue pour la 1re fois le {j.first_seen_at ? new Date(j.first_seen_at).toLocaleDateString("fr-FR") : "–"}
            </p>
            <a href={j.url} target="_blank" rel="noopener noreferrer"><button>Voir l'offre originale ↗</button></a>
          </>
        )}
      </aside>
    </div>
  );
}
