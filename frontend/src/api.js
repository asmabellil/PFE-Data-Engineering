// Client HTTP et gestion de session.
// - Jeton d'accès (15 min) gardé en MÉMOIRE uniquement : jamais dans localStorage/sessionStorage,
//   donc hors de portée d'un script injecté qui lirait le stockage du navigateur.
// - Jeton de renouvellement dans un cookie httpOnly posé par l'API : invisible pour le JavaScript.
// - Sur un 401 : une seule tentative de renouvellement (partagée entre requêtes simultanées),
//   puis la requête est rejouée ; si le renouvellement échoue, retour à la page de connexion.
let accessToken = null;

export const getToken = () => accessToken;
export const setToken = (t) => { accessToken = t || null; };

let refreshing = null;

export function refreshSession() {
  if (!refreshing) {
    refreshing = fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" })
      .then(async (res) => {
        if (!res.ok) { setToken(null); return null; }
        const data = await res.json();
        setToken(data.access_token);
        return data;
      })
      .catch(() => { setToken(null); return null; })
      .finally(() => { refreshing = null; });
  }
  return refreshing;
}

const send = (url, method, body) =>
  fetch(url, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

// Nombre de requêtes en cours : alimente la barre de chargement sous la navigation.
let inflight = 0;
const loadingListeners = new Set();

export function onLoadingChange(listener) {
  loadingListeners.add(listener);
  return () => loadingListeners.delete(listener);
}

function trackLoading(delta) {
  inflight = Math.max(0, inflight + delta);
  loadingListeners.forEach((listener) => listener(inflight > 0));
}

export async function api(path, options = {}) {
  trackLoading(1);
  try {
    return await request(path, options);
  } finally {
    trackLoading(-1);
  }
}

async function request(path, { method = "GET", body, params } = {}) {
  const qs = params
    ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString()
    : "";
  const url = `/api${path}${qs}`;
  let res = await send(url, method, body);
  if (res.status === 401 && !path.startsWith("/auth/")) {
    if (await refreshSession()) res = await send(url, method, body);
    if (res.status === 401) {
      setToken(null);
      window.location.assign("/login");
    }
  }
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) {
    const detail = Array.isArray(data?.detail) ? data.detail.map((d) => d.msg).join(", ") : data?.detail;
    throw new Error(detail || `Erreur ${res.status}`);
  }
  return data;
}

// libellés français des valeurs normalisées
export const LABELS = {
  full_time: "Temps plein / CDI", part_time: "Temps partiel", contract: "Contrat / mission",
  freelance: "Freelance", internship: "Stage", apprenticeship: "Alternance", temporary: "CDD / Temporaire",
  intern: "Stagiaire / étudiant", junior: "Junior", mid: "Confirmé", senior: "Senior", lead: "Lead / Manager",
  unknown: "Non renseigné", arbeitnow: "Arbeitnow", jobicy: "Jobicy", remotive: "Remotive",
  pythonorg: "Python.org", wttj: "Welcome to the Jungle", adzuna: "Adzuna", france_travail: "France Travail",
  valid: "Valides", quarantine: "Quarantaine", duplicate: "Doublons supprimés",
};
export const label = (v) => LABELS[v] ?? v ?? "Non renseigné";
export const fmtInt = (n) => (n ?? 0).toLocaleString("fr-FR");
export const fmtEur = (n) => (n ? `${Math.round(n / 1000).toLocaleString("fr-FR")} k€` : "–");
// Montant dans sa devise d'origine (ex. 130 000 $US) ; devise inconnue -> nombre seul
export function fmtMoney(n, currency) {
  if (n === null || n === undefined) return "–";
  try {
    return new Intl.NumberFormat("fr-FR", { style: "currency", currency, maximumFractionDigits: 0 }).format(n);
  } catch {
    return `${Math.round(n).toLocaleString("fr-FR")} ${currency || ""}`.trim();
  }
}
