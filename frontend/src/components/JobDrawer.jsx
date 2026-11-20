import { useEffect } from "react";
import { useApi } from "../context";
import { fmtEur, label } from "../api";
import Alert from "./Alert";
import { Skeleton } from "./charts";
import Icon from "./Icon";

// Badge à côté d'un titre de section : les éléments viennent de l'intitulé, faute de description
const TitleOnly = () => (
  <span className="tag warn" style={{ marginLeft: 8, verticalAlign: "middle" }} title="Déduit de l'intitulé, sans description">
    <Icon name="info" size={12} /> déduites du titre
  </span>
);

export default function JobDrawer({ id, onClose }) {
  const { data: j, loading, error } = useApi(`/jobs/${id}`);
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="drawer-bg" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={j?.title || "Fiche de l'offre"}>
        {/* barre fixe : le bouton reste cliquable et visible même en faisant défiler une longue description */}
        <div className="drawer-head">
          <button className="ghost icon-btn" onClick={onClose} aria-label="Fermer la fiche" title="Fermer (Échap)"><Icon name="x" size={18} /></button>
        </div>
        <div className="drawer-body">
        {loading && <Skeleton lines={6} label="Chargement de l'offre" />}
        {error && <div className="error" role="alert">{error}</div>}
        {j && (
          <div className="fade-in">
            <h1>{j.title}</h1>
            <p className="muted">
              {j.company} · {[j.city, j.country].filter(Boolean).join(", ") || j.location || "–"}
              {j.remote && <> · <Icon name="home" size={14} /> Télétravail</>}
            </p>
            <p>
              {j.contract_type && <span className="tag">{label(j.contract_type)}</span>}
              {j.experience_level && <span className="tag">{label(j.experience_level)}</span>}
              {j.industry && <span className={`tag${j.industry_source === "ml" ? " info" : ""}`}>{j.industry}{j.industry_source === "ml" ? " (prédit par IA)" : ""}</span>}
              {j.salary_annual_min_eur && <span className="tag"><Icon name="euro" size={12} /> {fmtEur(j.salary_annual_min_eur)} à {fmtEur(j.salary_annual_max_eur)} par an</span>}
            </p>
            {j.technologies?.length > 0 && <><h2>Technologies{!j.description && <TitleOnly />}</h2><p>{j.technologies.map((t) => <span key={t} className="tag">{t}</span>)}</p></>}
            {j.skills?.length > 0 && <><h2>Compétences{!j.description && <TitleOnly />}</h2><p>{j.skills.map((t) => <span key={t} className="tag">{t}</span>)}</p></>}
            <h2>Description</h2>
            {j.description ? <div className="desc">{j.description}</div> : (
              <Alert kind="info" dismissible={false}>
                {(j.sources || [j.source]).includes("wttj")
                  ? "Welcome to the Jungle ne permet pas aux robots de lire le détail de ses offres (accès refusé). "
                  : "La source ne fournit pas la description de cette offre. "}
                Les compétences ci-dessus sont déduites du seul intitulé. Consultez l'offre originale pour le détail.
              </Alert>
            )}
            <hr style={{ border: 0, borderTop: "1px solid var(--g150)", margin: "18px 0" }} />
            {/* attribution obligatoire (conditions d'utilisation des API) */}
            <p className="small">
              Source : {(j.sources || [j.source]).map(label).join(", ")} · publiée le {j.publication_date || "–"} ·
              vue pour la 1re fois le {j.first_seen_at ? new Date(j.first_seen_at).toLocaleDateString("fr-FR") : "–"}
            </p>
            <a href={j.url} target="_blank" rel="noopener noreferrer"><button>Voir l'offre originale <Icon name="external" size={14} /></button></a>
          </div>
        )}
        </div>
      </aside>
    </div>
  );
}
