// Client HTTP : ajoute le jeton JWT et gère l'expiration de session.
const TOKEN_KEY = "jobinsight_token";

export const getToken = () => sessionStorage.getItem(TOKEN_KEY);
export const setToken = (t) => (t ? sessionStorage.setItem(TOKEN_KEY, t) : sessionStorage.removeItem(TOKEN_KEY));

export async function api(path, { method = "GET", body, params } = {}) {
  const qs = params
    ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString()
    : "";
  const res = await fetch(`/api${path}${qs}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && !path.startsWith("/auth/")) {
    setToken(null);
    window.location.assign("/login");
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
};
export const label = (v) => LABELS[v] ?? v ?? "Non renseigné";
export const fmtInt = (n) => (n ?? 0).toLocaleString("fr-FR");
export const fmtEur = (n) => (n ? `${Math.round(n / 1000).toLocaleString("fr-FR")} k€` : "–");
