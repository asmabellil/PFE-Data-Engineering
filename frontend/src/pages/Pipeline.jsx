import { useApi, useAuth } from "../context";
import { fmtInt } from "../api";
import { COMPLETENESS_STATES, completenessColor, Donut, HBar, State } from "../components/charts";
import Icon from "../components/Icon";

// Un état porte toujours une couleur ET un mot (jamais la couleur seule)
const STATUS = {
  success: ["ok", "check", "réussie"], partial: ["warn", "alert", "partielle"],
  failed: ["ko", "x", "échec"], skipped: ["", "skip", "sautée"],
};
const GATE_LEVEL = {
  ok: ["ok", "check", "conforme"], warning: ["warn", "alert", "avertissement"], blocking: ["ko", "x", "bloquant"],
};

export default function Pipeline() {
  const { user } = useAuth();
  const runs = useApi("/admin/pipeline-runs", { limit: 15 });
  const reports = useApi("/admin/quality-reports", { limit: 10 });
  const summary = useApi("/admin/quality-summary");
  const users = useApi(user.role === "admin" ? "/admin/users" : "/auth/me");
  const audit = useApi(user.role === "admin" ? "/admin/audit" : "/auth/me", { limit: 20 });
  const lastReport = reports.data?.[0];
  const completeness = summary.data
    ? Object.entries(summary.data.completeness_pct).map(([label, jobs]) => ({ label, jobs })).sort((a, b) => b.jobs - a.jobs)
    : [];

  return (
    <>
      <h1>Pipeline & qualité des données</h1>
      <p className="muted" style={{ marginTop: 0 }}>Monitoring des exécutions Airflow, contrôles Data Quality et déduplication. Détail technique : Airflow (localhost:8080).</p>

      <div className="grid g2" style={{ marginBottom: 16 }}>
        <section className="card">
          <h2>Complétude des attributs (entrepôt)</h2>
          <div style={{ height: 300 }}>
            {completeness.length > 0 && (
              <HBar data={completeness} unit="%" formatter={(v) => `${v} %`} colorOf={(r) => completenessColor(r.jobs)}
                keyItems={COMPLETENESS_STATES.filter((st) => completeness.some((r) => completenessColor(r.jobs) === st.color))} />
            )}
          </div>
          {summary.data && <p className="muted small">{fmtInt(summary.data.jobs_seen_on_multiple_sources)} offres vues sur plusieurs sources (doublons inter-sources fusionnés).</p>}
        </section>
        <section className="card">
          <h2>Dernier rapport qualité</h2>
          <State loading={reports.loading} error={reports.error} empty={reports.data && !lastReport} />
          {lastReport && (
            <>
              <div style={{ height: 170 }}>
                <Donut
                  dimension="quality"
                  total={lastReport.records_total}
                  data={[
                    { label: "valid", jobs: lastReport.records_processed },
                    { label: "duplicate", jobs: lastReport.duplicates_removed },
                    { label: "quarantine", jobs: lastReport.records_quarantine },
                  ].filter((d) => d.jobs > 0)}
                />
              </div>
              <p className="small">
                Lot <b>{lastReport.run_id}</b> : {fmtInt(lastReport.records_total)} offres brutes → {fmtInt(lastReport.records_valid)} valides,
                {" "}{fmtInt(lastReport.records_quarantine)} en quarantaine, {fmtInt(lastReport.duplicates_removed)} doublons supprimés,
                {" "}<b>{fmtInt(lastReport.records_processed)}</b> offres traitées. Unicité : {lastReport.uniqueness_ok ? <span className="tag ok"><Icon name="check" size={12} /> respectée</span> : <span className="tag ko"><Icon name="x" size={12} /> doublons restants</span>} · Complétude moyenne : {Math.round(lastReport.avg_completeness * 100)} %
              </p>
              {lastReport.gate && (
                <div className="mb" style={{ marginBottom: 16 }}>
                  <div className="stat-label" style={{ marginBottom: 6 }}>Porte de qualité du lot</div>
                  {lastReport.gate.checks.map((c, i) => (
                    <div key={`${c.code}-${i}`} className="small" style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                      <span className={`tag ${GATE_LEVEL[c.level][0]}`}><Icon name={GATE_LEVEL[c.level][1]} size={12} /> {GATE_LEVEL[c.level][2]}</span>
                      <span>{c.message}</span>
                    </div>
                  ))}
                </div>
              )}
              <table>
                <thead><tr><th>Contrôle</th><th>Dimension</th><th>Occurrences</th></tr></thead>
                <tbody>{lastReport.issues.map((i) => <tr key={i.code}><td>{i.code}</td><td>{i.dimension}</td><td>{i.count}</td></tr>)}</tbody>
              </table>
            </>
          )}
        </section>
      </div>

      <section className="card" style={{ marginBottom: 16 }}>
        <h2>Exécutions du pipeline</h2>
        <State loading={runs.loading} error={runs.error} empty={runs.data && !runs.data.length} />
        <div className="table-wrap">
          <table>
            <thead><tr><th>Lot</th><th>Démarré</th><th>Tâches</th></tr></thead>
            <tbody>
              {runs.data?.map((r) => (
                <tr key={r.run_id}>
                  <td><b>{r.run_id}</b></td>
                  <td className="small">{new Date(r.started_at).toLocaleString("fr-FR")}</td>
                  <td className="small">
                    {Object.entries(r.tasks || {}).map(([t, v]) => (
                      <span key={t} className={`tag ${STATUS[v.status]?.[0] || ""}`} title={`${t} : ${STATUS[v.status]?.[2] || v.status}`}>
                        {STATUS[v.status] && <Icon name={STATUS[v.status][1]} size={12} />} {t}
                        {v.stats?.collected !== undefined && ` (${v.stats.collected})`}
                        {v.stats?.inserted !== undefined && ` (+${v.stats.inserted} / ~${v.stats.updated})`}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {user.role === "admin" && Array.isArray(users.data) && (
        <div className="grid g2">
          <section className="card">
            <h2>Utilisateurs</h2>
            <table><thead><tr><th>E-mail</th><th>Rôle</th><th>Dernière connexion</th></tr></thead>
              <tbody>{users.data.map((u) => <tr key={u.email}><td>{u.email}</td><td>{u.role}</td><td className="small">{u.last_login_at ? new Date(u.last_login_at).toLocaleString("fr-FR") : "–"}</td></tr>)}</tbody>
            </table>
          </section>
          <section className="card">
            <h2>Journal d'audit (sécurité)</h2>
            <table><thead><tr><th>Événement</th><th>Acteur</th><th>Date</th></tr></thead>
              <tbody>{Array.isArray(audit.data) && audit.data.map((a, i) => <tr key={i}><td>{a.event}</td><td>{a.actor}</td><td className="small">{new Date(a.at).toLocaleString("fr-FR")}</td></tr>)}</tbody>
            </table>
          </section>
        </div>
      )}
    </>
  );
}
