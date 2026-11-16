import { createContext, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";

const AuthCtx = createContext(null);
const FilterCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) return setReady(true);
    api("/auth/me").then(setUser).catch(() => setToken(null)).finally(() => setReady(true));
  }, []);

  const login = async (email, password, register = false, full_name = "") => {
    const data = await api(register ? "/auth/register" : "/auth/login", {
      method: "POST",
      body: register ? { email, password, full_name } : { email, password },
    });
    setToken(data.access_token);
    setUser(data.user);
  };
  const logout = () => { setToken(null); setUser(null); };
  return <AuthCtx.Provider value={{ user, ready, login, logout }}>{children}</AuthCtx.Provider>;
}

// filtres globaux (barre du haut) appliqués à tout le tableau de bord
export function FilterProvider({ children }) {
  const [filters, setFilters] = useState({ country: "", days: "" });
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
