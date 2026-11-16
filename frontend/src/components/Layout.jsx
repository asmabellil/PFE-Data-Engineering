import { NavLink, Outlet } from "react-router-dom";
import { useAuth, useFilters, useApi } from "../context";

const NAV = [
  ["/", "🏠", "Tableau de bord"],
  ["/offres", "💼", "Offres d'emploi"],
  ["/analyses", "📊", "Analyses"],
  ["/competences", "🧩", "Compétences"],
  ["/ia", "🤖", "IA & matching"],
  ["/pipeline", "⚙️", "Pipeline & qualité", "analyst"],
];
const ORDER = ["viewer", "analyst", "admin"];

export default function Layout() {
  const { user, logout } = useAuth();
  const { filters, setFilters } = useFilters();
  const { data: opts } = useApi("/jobs/filters");
  const { data: ov } = useApi("/analytics/overview");

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-logo" aria-hidden>
            <span style={{ height: 9 }} /><span style={{ height: 15 }} /><span style={{ height: 22 }} />
          </div>
          <div><b>Job<em>Insight</em></b><div className="muted small">Le marché de l'emploi en data</div></div>
        </div>
        <nav className="nav">
          {NAV.filter(([, , , role]) => !role || ORDER.indexOf(user.role) >= ORDER.indexOf(role)).map(([to, icon, txt]) => (
            <NavLink key={to} to={to} end={to === "/"}><span aria-hidden>{icon}</span>{txt}</NavLink>
          ))}
        </nav>
        <div className="foot">
          <b>Données mises à jour</b>
          <div className="muted">
            {ov?.last_update ? new Date(ov.last_update).toLocaleString("fr-FR") : "en attente du 1er run"}
          </div>
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <div className="filters" role="group" aria-label="Filtres globaux">
            <select value={filters.country} onChange={(e) => setFilters({ ...filters, country: e.target.value })} aria-label="Pays">
              <option value="">🌍 Tous les pays</option>
              {opts?.country?.map((c) => <option key={c}>{c}</option>)}
            </select>
            <select value={filters.days} onChange={(e) => setFilters({ ...filters, days: e.target.value })} aria-label="Période">
              <option value="">📅 Toute la période</option>
              <option value="7">7 derniers jours</option>
              <option value="30">30 derniers jours</option>
              <option value="90">3 derniers mois</option>
              <option value="180">6 derniers mois</option>
            </select>
          </div>
          <div className="user-chip">
            <div style={{ textAlign: "right" }}>
              <div><b>{user.full_name}</b></div>
              <div className="muted small">{user.role}</div>
            </div>
            <div className="avatar">{(user.full_name || user.email).slice(0, 2).toUpperCase()}</div>
            <button className="ghost" onClick={logout}>Déconnexion</button>
          </div>
        </div>
        <Outlet />
      </main>
    </div>
  );
}
