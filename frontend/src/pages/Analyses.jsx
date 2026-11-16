import { useApi, useFilters } from "../context";
import { fmtEur, fmtInt, label } from "../api";
import { ChartCard, Donut, HBar, State, VBar } from "../components/charts";

export default function Analyses() {
  const { filters } = useFilters();
  const contracts = useApi("/analytics/breakdown/contract", filters);
  const exp = useApi("/analytics/breakdown/experience", filters);
  const sources = useApi("/analytics/breakdown/source", filters);
  const cities = useApi("/analytics/breakdown/city", { ...filters, limit: 12 });
  const sal = useApi("/analytics/salaries", filters);
  const s = sal.data;

  return (
    <>
      <h1>Analyses du marché</h1>
      <p className="muted" style={{ marginTop: 0 }}>Contrats, niveaux d'expérience, localisation et salaires.</p>

      <div className="grid g2" style={{ marginBottom: 16 }}>
        <ChartCard title="Types de contrat" height={260}>
          {contracts.data && <Donut data={contracts.data} />}
        </ChartCard>
        <ChartCard title="Niveaux d'expérience" height={260}>
          {exp.data && <VBar data={exp.data} />}
        </ChartCard>
        <ChartCard title="Top villes" height={320}>
          {cities.data && <HBar data={cities.data.filter((d) => d.label !== "unknown")} />}
        </ChartCard>
        <ChartCard title="Offres par source de données" subtitle="Une offre vue sur plusieurs sources compte pour chacune" height={320}>
          {sources.data && <HBar data={sources.data} />}
        </ChartCard>
      </div>

      <h1 style={{ fontSize: "1.25rem", marginTop: 8 }}>Salaires</h1>
      <State loading={sal.loading} error={sal.error} empty={s && !s.count} />
      {s?.count > 0 && (
        <>
          <p className="muted">
            Basé sur {fmtInt(s.count)} offres publiant un salaire · salaire annuel moyen (milieu de fourchette) :
            <b> {fmtEur(s.average)}</b>. Montants convertis en EUR annuels (taux fixes, voir documentation).
          </p>
          <div className="grid g2">
            <ChartCard title="Distribution des salaires annuels" height={280}>
              <VBar data={s.distribution} x="range" />
            </ChartCard>
            <ChartCard title="Salaire moyen par niveau d'expérience" height={280}>
              <VBar data={s.by_experience} y="avg" formatter={fmtEur} />
            </ChartCard>
            <ChartCard title="Salaire moyen par technologie" subtitle="Technologies présentes dans au moins 3 offres avec salaire" height={360}>
              <HBar data={s.by_technology.slice(0, 12)} x="avg" formatter={fmtEur} />
            </ChartCard>
            <section className="card">
              <h2>Salaires par pays</h2>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Pays</th><th>Offres</th><th>Min</th><th>Moyenne</th><th>Max</th></tr></thead>
                  <tbody>
                    {s.by_country.map((r) => (
                      <tr key={r.label}><td>{label(r.label)}</td><td>{r.n}</td><td>{fmtEur(r.min)}</td><td><b>{fmtEur(r.avg)}</b></td><td>{fmtEur(r.max)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        </>
      )}
    </>
  );
}
