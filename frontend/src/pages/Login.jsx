import { useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context";
import Alert from "../components/Alert";
import Icon from "../components/Icon";

export default function Login() {
  const { user, login } = useAuth();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", full_name: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/" replace />;

  const submit = async (e) => {
    e.preventDefault();
    if (busy) return; // le bouton reste actif visuellement, mais un seul envoi à la fois
    setBusy(true); setError(null);
    try { await login(form.email, form.password, mode === "register", form.full_name); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const register = mode === "register";

  return (
    <div className="login-page">
      <form className="card login-card fade-in" onSubmit={submit}>
        <div>
          <div className="brand"><Icon name="compass" size={26} /><span>Job<em>Compass</em></span></div>
          <div className="brand-tagline">La boussole du marché de l'emploi</div>
        </div>
        <h1>{register ? "Créer un compte" : "Connexion"}</h1>
        {register && (
          <label className="field">Nom complet
            <input value={form.full_name} onChange={set("full_name")} required minLength={2} autoComplete="name" />
          </label>
        )}
        <label className="field">E-mail
          <input type="email" autoComplete="username" value={form.email} onChange={set("email")} required />
        </label>
        <label className="field">Mot de passe
          <input type="password" autoComplete={register ? "new-password" : "current-password"} value={form.password}
            onChange={set("password")} required minLength={register ? 8 : 1} />
          {register && <span className="hint">8 caractères minimum, avec au moins une lettre et un chiffre.</span>}
        </label>
        {error && <Alert key={error} kind="error">{error}</Alert>}
        <button aria-busy={busy}>{busy ? "Vérification…" : register ? "Créer le compte" : "Se connecter"}</button>
        <button type="button" className="ghost" onClick={() => { setMode(register ? "login" : "register"); setError(null); }}>
          {register ? "J'ai déjà un compte" : "Pas de compte ? S'inscrire"}
        </button>
      </form>
    </div>
  );
}
