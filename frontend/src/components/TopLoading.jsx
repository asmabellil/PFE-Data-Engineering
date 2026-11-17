// Barre de chargement sous la navigation : elle avance tant qu'une requête est en cours, sans jamais
// prétendre avoir fini, puis passe à 100 % et s'efface. Attendre ne doit jamais sembler bloqué.
import { useEffect, useState } from "react";
import { onLoadingChange } from "../api";

export default function TopLoading() {
  const [state, setState] = useState("idle"); // idle | loading | done

  useEffect(
    () => onLoadingChange((busy) => setState((prev) => (busy ? "loading" : prev === "loading" ? "done" : prev))),
    []
  );

  useEffect(() => {
    if (state !== "done") return undefined;
    const timer = setTimeout(() => setState("idle"), 500);
    return () => clearTimeout(timer);
  }, [state]);

  return (
    <div
      className={`top-loading top-loading--${state}`}
      role="progressbar"
      aria-label="Chargement des données"
      aria-busy={state === "loading"}
      aria-hidden={state === "idle"}
    >
      <div className="bar" />
    </div>
  );
}
