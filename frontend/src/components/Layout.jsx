import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useApi, useAuth, useFilters } from "../context";
import { currentTheme, toggleTheme } from "../theme";
import Icon from "./Icon";
import TopLoading from "./TopLoading";

const NAV = [
  ["/", "home", "Tableau de bord"],
  ["/offres", "briefcase", "Offres d'emploi"],
  ["/analyses", "chart", "Analyses"],
  ["/competences", "layers", "Compétences"],
  ["/ia", "sparkles", "IA et matching"],
  ["/pipeline", "activity", "Pipeline et qualité", "analyst"],
];
const ORDER = ["viewer", "analyst", "admin"];
const SIDEBAR_KEY = "jobcompass-sidebar";
const MOBILE = "(max-width: 1024px)";

// Préférence mémorisée du menu (ouvert / fermé). Sans stockage, le menu marche quand même.
const readCollapsed = () => {
  try { return localStorage.getItem(SIDEBAR_KEY) === "closed"; } catch { return false; }
};
const saveCollapsed = (closed) => {
  try { localStorage.setItem(SIDEBAR_KEY, closed ? "closed" : "open"); } catch { /* non mémorisé */ }
};

function useMediaQuery(query) {
  const [match, setMatch] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = (e) => setMatch(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);
  return match;
}

// Bouton de thème : l'icône montre le thème vers lequel on bascule
function ThemeToggle() {
  const [theme, setThemeState] = useState(currentTheme());
  useEffect(() => {
    const onChange = (e) => setThemeState(e.detail);
    window.addEventListener("themechange", onChange);
    return () => window.removeEventListener("themechange", onChange);
  }, []);
  const next = theme === "dark" ? "clair" : "sombre";
  return (
    <button className="ghost icon-btn" onClick={toggleTheme} aria-label={`Passer au thème ${next}`} title={`Thème ${next}`}>
      <Icon name={theme === "dark" ? "sun" : "moon"} size={18} />
    </button>
  );
}

// Menu du compte : s'ouvre depuis l'avatar, se ferme au clic à l'extérieur ou avec Échap
function UserMenu({ user, onLogout }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const name = user.full_name || user.email;
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);
  return (
    <div className="menu-anchor" ref={ref}>
      <button className="user-btn" onClick={() => setOpen(!open)} aria-haspopup="menu" aria-expanded={open}>
        <span className="avatar" aria-hidden>{name.slice(0, 2).toUpperCase()}</span>
        <span className="who"><b>{name}</b><span className="muted small">{user.role}</span></span>
        <Icon name="chevronDown" size={14} />
      </button>
      {open && (
        <div className="menu" role="menu">
          <div className="menu-head">
            <b>{name}</b>
            <div className="muted small">{user.email} · {user.role}</div>
          </div>
          <button role="menuitem" className="danger" onClick={() => { setOpen(false); onLogout(); }}>
            <Icon name="logout" size={16} /> Se déconnecter
          </button>
        </div>
      )}
    </div>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const { filters, setFilters } = useFilters();
  const { data: opts } = useApi("/jobs/filters");
  const { data: ov } = useApi("/analytics/overview");
  const isMobile = useMediaQuery(MOBILE);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();

  // sur petit écran, le menu se referme dès qu'on change de page ou qu'on appuie sur Échap
  useEffect(() => setMobileOpen(false), [location.pathname]);
  useEffect(() => {
    if (!mobileOpen) return undefined;
    const onKey = (e) => e.key === "Escape" && setMobileOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  const toggleMenu = () => {
    if (isMobile) return setMobileOpen(!mobileOpen);
    saveCollapsed(!collapsed);
    return setCollapsed(!collapsed);
  };
  const closed = !isMobile && collapsed;
  const menuOpen = isMobile ? mobileOpen : !collapsed;
  const freshness = ov?.last_update
    ? `Données mises à jour le ${new Date(ov.last_update).toLocaleString("fr-FR")}`
    : "En attente de la première collecte";

  return (
    <div className={`app${closed ? " sb-closed" : ""}${mobileOpen ? " sb-mobile-open" : ""}`}>
      <header className="topnav">
        <div className="topnav-inner">
          <button className="ghost icon-btn" onClick={toggleMenu} aria-label={menuOpen ? "Fermer le menu" : "Ouvrir le menu"}
            aria-expanded={menuOpen} aria-controls="sidebar">
            <Icon name="menu" size={20} />
          </button>
          <NavLink to="/" className="brand" aria-label="JobCompass, tableau de bord">
            <Icon name="compass" size={22} />
            <span>Job<em>Compass</em></span>
          </NavLink>
          <span className="spacer" />
          <ThemeToggle />
          <UserMenu user={user} onLogout={logout} />
        </div>
      </header>
      <TopLoading />

      <aside id="sidebar" className="sidebar" aria-label="Navigation principale">
        <nav>
          {NAV.filter(([, , , role]) => !role || ORDER.indexOf(user.role) >= ORDER.indexOf(role)).map(([to, icon, txt]) => (
            <NavLink key={to} to={to} end={to === "/"} title={closed ? txt : undefined} aria-label={txt}>
              <Icon name={icon} size={20} />
              <span className="label">{txt}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot" title={closed ? freshness : undefined}>
          <span className="dot" aria-hidden />
          <span className="label">{freshness}</span>
        </div>
      </aside>
      <div className="sidebar-backdrop" onClick={() => setMobileOpen(false)} aria-hidden />

      <div className="content">
        <main className="container">
          <div className="page-toolbar">
            <div className="filters" role="group" aria-label="Filtres appliqués à toutes les pages">
              <select value={filters.country} onChange={(e) => setFilters({ ...filters, country: e.target.value })} aria-label="Pays">
                <option value="">Tous les pays</option>
                {opts?.country?.map((c) => <option key={c}>{c}</option>)}
              </select>
              <select value={filters.days} onChange={(e) => setFilters({ ...filters, days: e.target.value })} aria-label="Période">
                <option value="">Toute la période</option>
                <option value="7">7 derniers jours</option>
                <option value="30">30 derniers jours</option>
                <option value="90">3 derniers mois</option>
                <option value="180">6 derniers mois</option>
              </select>
              <label className="switch" title="Masque les offres hors métiers Tech/Data (elles restent en base)">
                <input type="checkbox" role="switch" checked={filters.scope === "tech"}
                  onChange={(e) => setFilters({ ...filters, scope: e.target.checked ? "tech" : "all" })} />
                <span className="switch-track" aria-hidden><span className="switch-thumb" /></span>
                Tech/Data seulement
              </label>
            </div>
          </div>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
