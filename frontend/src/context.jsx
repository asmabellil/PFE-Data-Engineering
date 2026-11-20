import { createContext, useContext, useEffect, useState } from "react";
import { api, refreshSession, setToken } from "./api";

const AuthCtx = createContext(null);
const FilterCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  // au chargement de la page : le cookie httpOnly permet de reprendre la session sans ressaisir le mot de passe
  useEffect(() => {
    refreshSession().then((data) => data && setUser(data.user)).finally(() => setReady(true));
  }, []);

  const login = async (email, password, register = false, full_name = "") => {
    const data = await api(register ? "/auth/register" : "/auth/login", {
      method: "POST",
      body: register ? { email, password, full_name } : { email, password },
    });
    setToken(data.access_token);
    setUser(data.user);
  };
  // la session est révoquée côté serveur (refresh token), pas seulement oubliée par le navigateur
  const logout = async () => {
    try { await api("/auth/logout", { method: "POST" }); } catch { /* déjà expirée : rien à faire */ }
    setToken(null);
    setUser(null);
  };
  return <AuthCtx.Provider value={{ user, ready, login, logout }}>{children}</AuthCtx.Provider>;
}

// filtres globaux (barre du haut) appliqués à tout le tableau de bord.
// scope "tech" par défaut : seules les offres Tech/Data sont comptées (les autres restent en base).
export function FilterProvider({ children }) {
  const [filters, setFilters] = useState({ country: "", days: "", scope: "tech" });
  return <FilterCtx.Provider value={{ filters, setFilters }}>{children}</FilterCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
export const useFilters = () => useContext(FilterCtx);

// petit hook de chargement de données
export function useApi(path, params, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    api(path, { params })
      .then((data) => alive && setState({ data, loading: false, error: null }))
      .catch((e) => alive && setState({ data: null, loading: false, error: e.message }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, JSON.stringify(params), ...deps]);
  return state;
}
