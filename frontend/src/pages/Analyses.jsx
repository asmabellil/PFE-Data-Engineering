import { useApi, useFilters } from "../context";
import { fmtEur, fmtInt, fmtMoney, label } from "../api";
import Alert from "../components/Alert";
import { ChartCard, Donut, GradientKey, HBar, sequential, State, VBar } from "../components/charts";
import Icon from "../components/Icon";

// Un échantillon trop petit est signalé par un mot, pas seulement par une couleur
function SampleTag({ row, min }) {
  return row.low_sample
    ? <span className="tag warn" title={`Moins de ${min} offres : médiane peu fiable`}><Icon name="alert" size={12} /> peu d'offres</span>
    : <span className="tag ok"><Icon name="check" size={12} /> fiable</span>;
}

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
      <div className="page-head">
        <h1>Analyses du marché</h1>
        <p>Contrats, niveaux d'expérience, localisation et salaires.</p>
      </div>

      <div className="grid g2 mb">
        <ChartCard title="Types de contrat" icon="file" height={260} loading={contracts.loading}>
          {contracts.data && <Donut data={contracts.data} dimension="contract" />}
        </ChartCard>
        <ChartCard title="Niveaux d'expérience" icon="trending" subtitle="Du moins au plus expérimenté" height={260} loading={exp.loading}>
          {exp.data && <VBar data={exp.data} dimension="experience" />}
        </ChartCard>
        <ChartCard title="Top villes" icon="pin" height={320} loading={cities.loading}>
          {cities.data && <HBar data={cities.data.filter((d) => d.label !== "unknown")} />}
        </ChartCard>
        <ChartCard title="Offres par source de données" icon="layers" subtitle="Une offre vue sur plusieurs sources compte pour chacune" height={320} loading={sources.loading}>
          {sources.data && <HBar data={sources.data} dimension="source" />}
        </ChartCard>
      </div>

      <div className="page-head">
        <h2 style={{ margin: 0 }}>Salaires</h2>
        <p>Comparés d'abord dans la même devise, puis par pays, avec le nombre d'offres pour juger de la fiabilité.</p>
      </div>
      <State loading={sal.loading} error={sal.error} empty={s && !s.count} />
      {s?.count > 0 && (
        <>
          <Alert kind="info">
            Basé sur <b>{fmtInt(s.count)}</b> offres publiant un salaire. Une médiane calculée sur moins
            de {s.min_sample} offres est signalée « peu d'offres ». Les montants en euros sont convertis avec des taux fixes.
          </Alert>

          <section className="card mb">
            <div className="card-title"><Icon name="euro" size={20} /><h2>Médiane par devise</h2></div>
            <div className="card-sub">Salaire annuel, milieu de fourchette, dans la devise d'origine de l'offre</div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Devise</th><th>Offres</th><th>Médiane (devise d'origine)</th><th>Équivalent €</th><th>Min</th><th>Max</th><th>Fiabilité</th></tr></thead>
                <tbody>
                  {s.by_currency.map((r) => (
                    <tr key={r.currency}>
                      <td><b className="mono">{r.currency}</b></td>
                      <td>{fmtInt(r.n)}</td>
                      <td><b>{fmtMoney(r.median, r.currency)}</b></td>
                      <td>{fmtEur(r.median_eur)}</td>
                      <td>{fmtMoney(r.min, r.currency)}</td>
                      <td>{fmtMoney(r.max, r.currency)}</td>
                      <td><SampleTag row={r} min={s.min_sample} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <div className="grid g2">
            <section className="card">
              <div className="card-title"><Icon name="globe" size={20} /><h2>Médiane par pays</h2></div>
              <div className="card-sub">Converti en euros annuels pour pouvoir comparer les pays</div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Pays</th><th>Offres</th><th>Médiane</th><th>Min</th><th>Max</th><th>Fiabilité</th></tr></thead>
                  <tbody>
                    {s.median_by_country.map((r) => (
                      <tr key={r.label}>
                        <td>{label(r.label)}</td><td>{fmtInt(r.n)}</td><td><b>{fmtEur(r.median)}</b></td>
                        <td>{fmtEur(r.min)}</td><td>{fmtEur(r.max)}</td><td><SampleTag row={r} min={s.min_sample} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <ChartCard title="Distribution des salaires annuels" icon="chart" subtitle="En euros, toutes devises converties" height={300}>
              <VBar data={s.distribution} x="range" colorOf={(r, i) => sequential(i, s.distribution.length)}
                keyNode={<GradientKey low="Salaires les plus bas" high="les plus hauts" />} />
            </ChartCard>
            <ChartCard title="Salaire moyen par niveau d'expérience" icon="trending" height={300}>
              <VBar data={s.by_experience} y="avg" formatter={fmtEur} dimension="experience" />
            </ChartCard>
            <ChartCard title="Salaire moyen par technologie" icon="cpu" subtitle="Technologies présentes dans au moins 3 offres avec salaire" height={360}>
              <HBar data={s.by_technology.slice(0, 12)} x="avg" formatter={fmtEur} />
            </ChartCard>
          </div>
        </>
      )}
    </>
  );
}
