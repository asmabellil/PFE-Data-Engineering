import { useApi, useAuth } from "../context";
import { fmtInt } from "../api";
import { HBar, State } from "../components/charts";

const STATUS = { success: "✅", partial: "⚠️", failed: "❌", skipped: "⏭️" };

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
            {completeness.length > 0 && <HBar data={completeness} unit="%" formatter={(v) => `${v} %`} />}
          </div>
          {summary.data && <p className="muted small">{fmtInt(summary.data.jobs_seen_on_multiple_sources)} offres vues sur plusieurs sources (doublons inter-sources fusionnés).</p>}
        </section>
        <section className="card">
          <h2>Dernier rapport qualité</h2>
          <State loading={reports.loading} error={reports.error} empty={reports.data && !lastReport} />
          {lastReport && (
            <>
              <p className="small">
                Lot <b>{lastReport.run_id}</b> : {fmtInt(lastReport.records_total)} offres brutes → {fmtInt(lastReport.records_valid)} valides,
                {" "}{fmtInt(lastReport.records_quarantine)} en quarantaine, {fmtInt(lastReport.duplicates_removed)} doublons supprimés,
                {" "}<b>{fmtInt(lastReport.records_processed)}</b> offres traitées. Unicité : {lastReport.uniqueness_ok ? "✅" : "❌"} · Complétude moyenne : {Math.round(lastReport.avg_completeness * 100)} %
              </p>
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
                      <span key={t} className="tag" title={JSON.stringify(v.stats)}>
                        {STATUS[v.status] || "•"} {t}
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
