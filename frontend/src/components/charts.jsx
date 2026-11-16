// Composants graphiques communs (Recharts).
// Règles appliquées : une seule teinte pour une série unique (pas de légende), palette
// catégorielle dans un ordre fixe pour les séries multiples (légende + étiquettes),
// marques fines, grille discrète, info-bulle au survol, jamais de double axe.
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { fmtInt, label } from "../api";

export const PRIMARY = "var(--primary)";
// ordre catégoriel fixe (la couleur suit l'entité, jamais son rang)
export const CATEGORICAL = ["#2563eb", "#e8862a", "#0f9d8f", "#7c5cd6", "#d6517d", "#8a9a2b", "#3aa0d8", "#9a6b3f"];
const axis = { stroke: "var(--muted)", fontSize: 12, tickLine: false, axisLine: false };

function Tip({ active, payload, label: l, unit = "offres", formatter }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tip">
      {l !== undefined && <div><b>{label(l)}</b></div>}
      {payload.map((p) => (
        <div key={p.dataKey + p.name}>
          {payload.length > 1 && <i style={{ display: "inline-block", width: 8, height: 8, background: p.color, borderRadius: 2, marginRight: 6 }} />}
          {payload.length > 1 ? `${p.name} : ` : ""}{formatter ? formatter(p.value) : `${fmtInt(p.value)} ${unit}`}
        </div>
      ))}
    </div>
  );
}

export function ChartCard({ title, subtitle, children, height = 280 }) {
  return (
    <section className="card">
      <h2>{title}</h2>
      {subtitle && <div className="muted small" style={{ marginTop: -8, marginBottom: 8 }}>{subtitle}</div>}
      <div style={{ height }}>{children}</div>
    </section>
  );
}

export function HBar({ data, x = "jobs", y = "label", unit, formatter, color = PRIMARY, onClick }) {
  return (
    <ResponsiveContainer>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }} barCategoryGap={4}>
        <CartesianGrid horizontal={false} stroke="var(--grid)" />
        <XAxis type="number" {...axis} tickFormatter={formatter} />
        <YAxis type="category" dataKey={y} width={150} {...axis} tickFormatter={label} interval={0} />
        <Tooltip content={<Tip unit={unit} formatter={formatter} />} cursor={{ fill: "var(--surface-2)" }} />
        <Bar dataKey={x} fill={color} radius={[0, 4, 4, 0]} maxBarSize={18} onClick={onClick} style={{ cursor: onClick ? "pointer" : "default" }} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function VBar({ data, x = "label", y = "jobs", unit, formatter }) {
  return (
    <ResponsiveContainer>
      <BarChart data={data} margin={{ top: 8, right: 8 }}>
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        <XAxis dataKey={x} {...axis} tickFormatter={label} interval={0} angle={data?.length > 6 ? -25 : 0} textAnchor={data?.length > 6 ? "end" : "middle"} height={data?.length > 6 ? 60 : 30} />
        <YAxis {...axis} tickFormatter={formatter} width={60} />
        <Tooltip content={<Tip unit={unit} formatter={formatter} />} cursor={{ fill: "var(--surface-2)" }} />
        <Bar dataKey={y} fill={PRIMARY} radius={[4, 4, 0, 0]} maxBarSize={36} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function TimeArea({ data, x = "period", y = "jobs" }) {
  return (
    <ResponsiveContainer>
      <AreaChart data={data} margin={{ top: 8, right: 12 }}>
        <defs>
          <linearGradient id="fillArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2563eb" stopOpacity={0.25} />
            <stop offset="100%" stopColor="#2563eb" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        <XAxis dataKey={x} {...axis} minTickGap={24} />
        <YAxis {...axis} width={44} allowDecimals={false} />
        <Tooltip content={<Tip />} cursor={{ stroke: "var(--muted)", strokeDasharray: "3 3" }} />
        <Area type="monotone" dataKey={y} stroke="#2563eb" strokeWidth={2} fill="url(#fillArea)" activeDot={{ r: 5 }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function MultiLine({ data, keys, x = "period" }) {
  return (
    <ResponsiveContainer>
      <LineChart data={data} margin={{ top: 8, right: 12 }}>
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        <XAxis dataKey={x} {...axis} minTickGap={24} />
        <YAxis {...axis} width={40} allowDecimals={false} />
        <Tooltip content={<Tip />} cursor={{ stroke: "var(--muted)", strokeDasharray: "3 3" }} />
        <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
        {keys.map((k, i) => (
          <Line key={k} dataKey={k} name={k} stroke={CATEGORICAL[i % CATEGORICAL.length]} strokeWidth={2} dot={false} activeDot={{ r: 4 }} connectNulls />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

// Donut avec légende obligatoire (>= 2 catégories) ; au-delà de 7, regroupement en "Autres"
export function Donut({ data, total }) {
  const top = data.slice(0, 7);
  const rest = data.slice(7).reduce((s, d) => s + d.jobs, 0);
  const rows = rest ? [...top, { label: "Autres", jobs: rest }] : top;
  const sum = rows.reduce((s, d) => s + d.jobs, 0) || 1;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(140px, 1fr) 1.2fr", alignItems: "center", height: "100%" }}>
      <ResponsiveContainer>
        <PieChart>
          <Pie data={rows} dataKey="jobs" nameKey="label" innerRadius="62%" outerRadius="92%" stroke="var(--surface)" strokeWidth={2}>
            {rows.map((r, i) => <Cell key={r.label} fill={r.label === "Autres" ? "#9aa3b2" : CATEGORICAL[i]} />)}
          </Pie>
          <Tooltip content={<Tip />} />
          {total !== undefined && (
            <text x="50%" y="50%" textAnchor="middle" dominantBaseline="middle" fill="var(--text)" fontWeight="700" fontSize="18">{fmtInt(total)}</text>
          )}
        </PieChart>
      </ResponsiveContainer>
      <div className="legend" style={{ flexDirection: "column" }}>
        {rows.map((r, i) => (
          <div key={r.label} style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
            <span><i style={{ background: r.label === "Autres" ? "#9aa3b2" : CATEGORICAL[i] }} />{label(r.label)}</span>
            <b>{Math.round((100 * r.jobs) / sum)} %</b>
          </div>
        ))}
      </div>
    </div>
  );
}

export function State({ loading, error, empty }) {
  if (loading) return <div className="muted small">Chargement…</div>;
  if (error) return <div className="error">{error}</div>;
  if (empty) return <div className="muted small">Pas encore de données – lancez le pipeline (DAG jobinsight_pipeline dans Airflow).</div>;
  return null;
}
