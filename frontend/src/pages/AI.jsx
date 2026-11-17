import { useState } from "react";
import { api, fmtEur, label } from "../api";
import { useApi, useAuth, useFilters } from "../context";
import Alert, { DoneCheck } from "../components/Alert";
import Icon from "../components/Icon";

function JobResult({ j }) {
  return (
    <div className="result">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
        <div>
          <a href={j.url} target="_blank" rel="noopener noreferrer"><b>{j.title}</b></a>
          <div className="muted small">{j.company} · {[j.city, j.country].filter(Boolean).join(", ") || (j.remote ? "Télétravail" : "–")} · {label(j.source)}</div>
        </div>
        <div className="score" title="Score de pertinence">{Math.round(j.score * 100)} %</div>
      </div>
      {j.matched_technologies ? (
        <div style={{ marginTop: 6 }}>
          {j.matched_technologies.map((t) => <span key={t} className="tag ok"><Icon name="check" size={12} /> {t}</span>)}
          {j.missing_technologies.slice(0, 6).map((t) => <span key={t} className="tag miss"><Icon name="x" size={12} /> {t}</span>)}
        </div>
      ) : (
        <div style={{ marginTop: 6 }}>{j.technologies?.slice(0, 6).map((t) => <span key={t} className="tag">{t}</span>)}</div>
      )}
    </div>
  );
}

function useAction() {
  const [state, setState] = useState({ data: null, busy: false, error: null });
  const run = async (fn) => {
    if (state.busy) return; // un seul calcul à la fois (le bouton reste visible, il se remplit)
    setState({ data: null, busy: true, error: null });
    try { setState({ data: await fn(), busy: false, error: null }); }
    catch (e) { setState({ data: null, busy: false, error: e.message }); }
  };
  return [state, run];
}

function SemanticSearch() {
  const { filters } = useFilters();
  const [q, setQ] = useState("ingénieur données cloud");
  const [s, run] = useAction();
  return (
    <section className="card">
      <div className="card-title"><Icon name="search" size={20} /><h2>Recherche sémantique (Deep Learning)</h2></div>
      <p className="muted small">Le texte est transformé en vecteur par un modèle Transformer multilingue : « ingénieur données » retrouve aussi « Data Engineer » ou « Dateningenieur ».</p>
      <form className="toolbar" onSubmit={(e) => { e.preventDefault(); run(() => api("/ai/search", { method: "POST", body: { query: q, k: 10, country: filters.country || null } })); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: 1 }} maxLength={500} />
        <button aria-busy={s.busy}>{s.busy ? "Recherche…" : "Rechercher"}</button>
      </form>
      {s.error && <Alert key={s.error} kind="error">{s.error}</Alert>}
      {s.data?.results?.length === 0 && <div className="muted">Index vide : l'indexation des offres est peut-être en cours.</div>}
      {s.data?.results?.map((j) => <JobResult key={j.dedup_key} j={j} />)}
    </section>
  );
}

const CV_EXAMPLE = `Étudiante en Master 2 Data Engineering. Compétences : Python, SQL, Apache Spark, Kafka, Airflow, Docker, MongoDB, Power BI. Projet de fin d'études : plateforme Big Data de collecte d'offres d'emploi. Anglais courant, travail en équipe, autonomie.`;

// Zone de dépôt : un CV au format texte est lu dans le navigateur (rien n'est envoyé avant le clic sur le bouton)
function CvDropZone({ onText }) {
  const [over, setOver] = useState(false);
  const [note, setNote] = useState(null);
  const read = (file) => {
    if (!file) return;
    if (!/\.(txt|md)$/i.test(file.name) && !file.type.startsWith("text/")) {
      setNote("Format non pris en charge : déposez un fichier texte (.txt ou .md) ou collez le contenu du CV ci-dessous.");
      return;
    }
    file.text().then((t) => { onText(t.slice(0, 20000)); setNote(`« ${file.name} » chargé.`); });
  };
  return (
    <>
      <label
        className={`dropzone${over ? " over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); read(e.dataTransfer.files[0]); }}
      >
        <Icon name="upload" size={22} />
        <span><b>Déposez un CV ici</b> ou cliquez pour choisir un fichier texte</span>
        <input type="file" accept=".txt,.md,text/plain" onChange={(e) => read(e.target.files[0])} />
      </label>
      {note && <p className="small muted fade-in">{note}</p>}
    </>
  );
}

function CvMatching() {
  const { filters } = useFilters();
  const [cv, setCv] = useState(CV_EXAMPLE);
  const [s, run] = useAction();
  return (
    <section className="card">
      <div className="card-title"><Icon name="file" size={20} /><h2>Matching CV et offres</h2></div>
      <p className="muted small">Déposez ou collez le texte d'un CV. Score = 70 % similarité sémantique + 30 % technologies en commun. Le CV n'est pas enregistré.</p>
      <CvDropZone onText={setCv} />
      <textarea rows={6} value={cv} onChange={(e) => setCv(e.target.value)} maxLength={20000} aria-label="Texte du CV" />
      <div className="toolbar" style={{ marginTop: 8 }}>
        <button aria-busy={s.busy} onClick={() => run(() => api("/ai/match-cv", { method: "POST", body: { cv_text: cv, k: 10, country: filters.country || null } }))}>
          {s.busy ? "Analyse…" : "Trouver les offres adaptées"}
        </button>
      </div>
      {s.error && <Alert key={s.error} kind="error">{s.error}</Alert>}
      {s.data && (
        <>
          <p className="small"><b>Technologies détectées dans le CV :</b> {s.data.cv_technologies.map((t) => <span key={t} className="tag ok">{t}</span>)}</p>
          {s.data.recommended_skills.length > 0 && (
            <p className="small"><b>À apprendre en priorité (demandées par ces offres) :</b> {s.data.recommended_skills.map((r) => <span key={r.technology} className="tag miss">{r.technology} · {r.in_jobs}</span>)}</p>
          )}
          {s.data.results.map((j) => <JobResult key={j.dedup_key} j={j} />)}
        </>
      )}
    </section>
  );
}

function SalaryPredictor() {
  const opts = useApi("/jobs/filters").data;
  const [f, setF] = useState({ title: "Data Engineer", technologies: "Python, SQL, Apache Spark, AWS", experience_level: "mid", country: "", contract_type: "full_time", remote: false });
  const [s, run] = useAction();
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const submit = (e) => {
    e.preventDefault();
    run(() => api("/ai/predict-salary", { method: "POST", body: { ...f, country: f.country || null, technologies: f.technologies.split(",").map((t) => t.trim()).filter(Boolean) } }));
  };
  return (
    <section className="card">
      <div className="card-title"><Icon name="euro" size={20} /><h2>Estimation de salaire (Machine Learning)</h2></div>
      <form className="grid" style={{ gap: 8 }} onSubmit={submit}>
        <input value={f.title} onChange={set("title")} placeholder="Intitulé du poste" required />
        <input value={f.technologies} onChange={set("technologies")} placeholder="Technologies (séparées par des virgules)" />
        <div className="toolbar" style={{ margin: 0 }}>
          <select value={f.experience_level} onChange={set("experience_level")}>
            {["intern", "junior", "mid", "senior", "lead"].map((v) => <option key={v} value={v}>{label(v)}</option>)}
          </select>
          <select value={f.country} onChange={set("country")}><option value="">Pays (indifférent)</option>{opts?.country?.map((c) => <option key={c}>{c}</option>)}</select>
          <label className="small"><input type="checkbox" checked={f.remote} onChange={set("remote")} /> Télétravail</label>
          <button aria-busy={s.busy}>Estimer</button>
        </div>
      </form>
      {s.error && <Alert key={s.error} kind="error">{s.error}</Alert>}
      {s.data && (
        <p style={{ fontSize: "1.1rem" }}>
          Estimation : <b>{fmtEur(s.data.salary_eur)}</b> / an
          <span className="muted small"> (intervalle {fmtEur(s.data.low_eur)} – {fmtEur(s.data.high_eur)}, erreur moyenne ± {fmtEur(s.data.mae_eur)}, modèle {s.data.model})</span>
        </p>
      )}
    </section>
  );
}

function Classifier() {
  const [text, setText] = useState("We are looking for a backend engineer to build REST APIs in Go and PostgreSQL on Kubernetes.");
  const [s, run] = useAction();
  return (
    <section className="card">
      <div className="card-title"><Icon name="tag" size={20} /><h2>Classification du secteur (ML et Deep Learning)</h2></div>
      <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="toolbar" style={{ marginTop: 8 }}>
        <button aria-busy={s.busy} onClick={() => run(() => api("/ai/classify", { method: "POST", body: { text } }))}>Classer</button>
      </div>
      {s.error && <Alert key={s.error} kind="error">{s.error}</Alert>}
      {s.data && (
        <div className="grid g2">
          {["ml_tfidf", "dl_mlp"].filter((k) => s.data[k]).map((k) => (
            <div key={k}>
              <div className="muted small">{k === "ml_tfidf" ? `ML : TF-IDF + ${s.data[k].model}` : "DL : MLP sur embeddings Transformer"}</div>
              {s.data[k].top3.map((t) => <div key={t.industry}>{t.industry} – <b>{Math.round(t.proba * 100)} %</b></div>)}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function ModelsPanel() {
  const { user } = useAuth();
  const models = useApi("/ai/models");
  const clusters = useApi("/ai/clusters");
  const status = useApi("/ai/status");
  const [msg, setMsg] = useState(null);
  const trigger = async (path) => {
    setMsg(null);
    try { await api(path, { method: "POST" }); setMsg({ ok: true, text: "Tâche lancée en arrière-plan." }); }
    catch (e) { setMsg({ ok: false, text: e.message }); }
  };
  return (
    <section className="card">
      <div className="card-title"><Icon name="trending" size={20} /><h2>Modèles et métriques</h2></div>
      {status.data && <p className="muted small">Index sémantique : {status.data.indexed_jobs} / {status.data.total_jobs} offres encodées · modèle {status.data.embedding_model}</p>}
      {user.role === "admin" && (
        <div className="toolbar">
          <button className="ghost" onClick={() => trigger("/ai/reindex")}>Ré-indexer les embeddings</button>
          <button className="ghost" onClick={() => trigger("/ai/train-dl")}>Entraîner le réseau de neurones</button>
          {msg?.ok && <span className="status-line"><DoneCheck /> {msg.text}</span>}
          {msg && !msg.ok && <Alert key={msg.text} kind="error">{msg.text}</Alert>}
        </div>
      )}
      {models.data?.length === 0 && <p className="muted">Aucun modèle entraîné : lancez le DAG « jobinsight_ml » dans Airflow.</p>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Modèle</th><th>Meilleur algo</th><th>Métriques</th><th>Entraîné le</th></tr></thead>
          <tbody>
            {models.data?.map((m) => (
              <tr key={m.model}>
                <td><b>{m.model}</b></td>
                <td>{m.metrics.best_model || m.metrics.architecture || (m.metrics.best_k ? `K-Means k=${m.metrics.best_k}` : "–")}</td>
                <td className="small">
                  {m.metrics.comparison && Object.entries(m.metrics.comparison).map(([k, v]) => <div key={k}>{k} : {Object.entries(v).map(([a, b]) => `${a}=${b}`).join(", ")}</div>)}
                  {m.metrics.f1_macro !== undefined && <div>accuracy={m.metrics.accuracy}, f1_macro={m.metrics.f1_macro}</div>}
                  {m.metrics.silhouette !== undefined && <div>silhouette={m.metrics.silhouette}</div>}
                </td>
                <td className="small">{new Date(m.created_at).toLocaleString("fr-FR")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {clusters.data?.length > 0 && (
        <>
          <h2 style={{ marginTop: 16 }}>Familles de métiers (clustering K-Means)</h2>
          {clusters.data.map((c) => (
            <div key={c.cluster_id} className="result">
              <b>{c.label}</b> <span className="muted small">· {c.size} offres</span>
              <div>{c.top_technologies.map((t) => <span key={t} className="tag">{t}</span>)}</div>
            </div>
          ))}
        </>
      )}
    </section>
  );
}

export default function AI() {
  const [tab, setTab] = useState("cv");
  const TABS = [["cv", "Matching CV"], ["search", "Recherche sémantique"], ["salary", "Salaire"], ["classify", "Classification"], ["models", "Modèles"]];
  return (
    <>
      <h1>Intelligence artificielle</h1>
      <p className="muted" style={{ marginTop: 0 }}>Machine Learning (scikit-learn) et Deep Learning (Transformers / PyTorch) appliqués aux offres collectées.</p>
      <div className="tabs">{TABS.map(([k, t]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{t}</button>)}</div>
      {tab === "cv" && <CvMatching />}
      {tab === "search" && <SemanticSearch />}
      {tab === "salary" && <SalaryPredictor />}
      {tab === "classify" && <Classifier />}
      {tab === "models" && <ModelsPanel />}
    </>
  );
}
