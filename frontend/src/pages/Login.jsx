import { useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context";

export default function Login() {
  const { user, login } = useAuth();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", full_name: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/" replace />;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await login(form.email, form.password, mode === "register", form.full_name); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="login-page">
      <form className="card login-card" onSubmit={submit}>
        <div className="brand" style={{ padding: 0 }}>
          <div className="brand-logo" aria-hidden><span style={{ height: 9 }} /><span style={{ height: 15 }} /><span style={{ height: 22 }} /></div>
          <div><b>Job<em>Insight</em></b><div className="muted small">Plateforme Big Data d'analyse des offres d'emploi</div></div>
        </div>
        <h1>{mode === "login" ? "Connexion" : "Créer un compte"}</h1>
        {mode === "register" && <input placeholder="Nom complet" value={form.full_name} onChange={set("full_name")} required minLength={2} />}
        <input type="email" placeholder="E-mail" autoComplete="username" value={form.email} onChange={set("email")} required />
        <input type="password" placeholder="Mot de passe" autoComplete={mode === "login" ? "current-password" : "new-password"} value={form.password} onChange={set("password")} required minLength={mode === "register" ? 8 : 1} />
        {mode === "register" && <div className="muted small">8 caractères minimum, au moins une lettre et un chiffre.</div>}
        {error && <div className="error">{error}</div>}
        <button disabled={busy}>{busy ? "…" : mode === "login" ? "Se connecter" : "Créer le compte"}</button>
        <button type="button" className="ghost" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}>
          {mode === "login" ? "Pas de compte ? S'inscrire" : "J'ai déjà un compte"}
        </button>
      </form>
    </div>
  );
}
