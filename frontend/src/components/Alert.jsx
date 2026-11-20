// Alerte : fond clair et bordure de la même teinte, icône + texte (la couleur n'est jamais le seul signal),
// croix de fermeture discrète quand l'alerte peut être refermée.
import { useState } from "react";
import Icon from "./Icon";

const ICONS = { error: "alert", warn: "alert", info: "info", success: "check" };

export default function Alert({ kind = "error", children, dismissible = true }) {
  const [open, setOpen] = useState(true);
  if (!open) return null;
  return (
    <div className={`alert alert-${kind} fade-in`} role={kind === "error" ? "alert" : "status"}>
      <Icon name={ICONS[kind]} size={16} />
      <div className="alert-body">{children}</div>
      {dismissible && (
        <button type="button" className="alert-close" onClick={() => setOpen(false)} aria-label="Fermer le message">
          <Icon name="x" size={14} />
        </button>
      )}
    </div>
  );
}

// Coche « terminé » : une pastille verte apparaît avec un léger rebond, puis la coche se dessine
export function DoneCheck() {
  return (
    <span className="done" aria-hidden>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
        <path d="m5 12 5 5L20 7" />
      </svg>
    </span>
  );
}
