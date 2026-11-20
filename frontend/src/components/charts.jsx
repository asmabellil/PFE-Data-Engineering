// Composants graphiques communs (Recharts).
// Code couleur :
// - une couleur suit toujours la même entité, sur toutes les pages (CDI, France Travail...), jamais son rang ;
// - une seule série = rouge de l'application, sans clé (le titre suffit) ;
// - catégories sans ordre (sources, contrats, familles de métiers) = palette catégorielle fixe + clé ;
// - catégories ordonnées (expérience, salaires) = dégradé de rouge + clé dans l'ordre ;
// - états (qualité) = couleurs d'état (vert, rouge, ambre), toujours accompagnées du mot.
// Les couleurs sont des variables CSS : les graphiques suivent le thème clair ou sombre sans être redessinés.
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { fmtInt, label } from "../api";
import Alert from "./Alert";
import Icon from "./Icon";

// Série unique : rouge de l'application (choix de Yacine), comme le reste de l'interface.
export const PRIMARY = "var(--red)";
// Repli pour une entité sans couleur attribuée. Vert et ambre sont exclus : ils signalent des états.
export const CATEGORICAL = [
  "var(--red)", "var(--purple)", "var(--cyan)", "var(--orange)", "var(--pink)", "var(--teal)", "var(--lime)",
];
const OTHERS = "var(--g300)";

// Couleur attribuée à chaque entité, identique sur tous les graphiques
export const PALETTES = {
  source: {
    france_travail: "var(--red)", adzuna: "var(--purple)", wttj: "var(--cyan)", arbeitnow: "var(--orange)",
    jobicy: "var(--pink)", remotive: "var(--teal)", pythonorg: "var(--lime)",
  },
  contract: {
    full_time: "var(--red)", temporary: "var(--cyan)", freelance: "var(--orange)", internship: "var(--purple)",
    apprenticeship: "var(--pink)", part_time: "var(--teal)", contract: "var(--lime)",
  },
  experience: {
    intern: "var(--seq-1)", junior: "var(--seq-2)", mid: "var(--seq-3)", senior: "var(--seq-4)", lead: "var(--seq-5)",
  },
  industry: {
    "Développement logiciel": "var(--red)", "Data & IA": "var(--purple)", "DevOps & Cloud": "var(--cyan)",
    "Cybersécurité": "var(--orange)", "Commercial & Vente": "var(--pink)", "Produit & Gestion de projet": "var(--teal)",
    "Marketing & Communication": "var(--lime)", "Design & UX": "var(--indigo)", "Support client": "var(--brown)",
    "Finance & Comptabilité": "var(--slate)", "RH & Recrutement": "var(--olive)", "Rédaction & Contenu": "var(--g400)",
  },
  quality: { valid: "var(--green)", quarantine: "var(--red)", duplicate: "var(--amber)" },
  techCategory: {
    Langage: "var(--red)", Framework: "var(--purple)", Cloud: "var(--cyan)", DevOps: "var(--orange)",
    "Base de données": "var(--pink)", "Data / Big Data": "var(--teal)", "IA / ML": "var(--indigo)",
    "BI / Visualisation": "var(--lime)", Outil: "var(--slate)",
  },
};

// Dégradé pour des valeurs ordonnées (tranches de salaire...) : la i-ème barre sur n prend une des 5 teintes
export const sequential = (i, n) => `var(--seq-${Math.min(5, Math.max(1, Math.ceil(((i + 1) / Math.max(n, 1)) * 5)))})`;

// États de complétude : la couleur est toujours accompagnée d'un mot dans la clé
export const COMPLETENESS_STATES = [
  { label: "Bon (80 % et plus)", color: "var(--green)", min: 80 },
  { label: "Moyen (50 à 80 %)", color: "var(--amber)", min: 50 },
  { label: "Faible (moins de 50 %)", color: "var(--red)", min: 0 },
];
export const completenessColor = (pct) => COMPLETENESS_STATES.find((s) => pct >= s.min).color;
// Ordre d'affichage des catégories ordonnées (la clé et les barres suivent cet ordre)
export const ORDERS = { experience: ["intern", "junior", "mid", "senior", "lead", "unknown"] };

export function colorFor(dimension, key, index = 0) {
  if (key === "Autres" || key === "unknown" || key === null || key === undefined) return OTHERS;
  return PALETTES[dimension]?.[key] ?? CATEGORICAL[index % CATEGORICAL.length];
}

export function sortByOrder(data, dimension, key = "label") {
  const order = ORDERS[dimension];
  if (!order || !data) return data;
  const rank = (v) => (order.indexOf(v) === -1 ? order.length : order.indexOf(v));
  return [...data].sort((a, b) => rank(a[key]) - rank(b[key]));
}

const axis = { stroke: "var(--g400)", fontSize: 12, tickLine: false, axisLine: false };

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

// Clé : un carré de couleur, le libellé et la valeur, dans l'ordre des données
export function Key({ items, formatter }) {
  return (
    <div className="chart-key" role="list" aria-label="Légende">
      {items.map((it) => (
        <span key={it.label} role="listitem">
          <i style={{ display: "inline-block", width: 10, height: 10, borderRadius: 3, marginRight: 6, background: it.color }} />
          {label(it.label)}{it.value !== undefined && <b>{formatter ? formatter(it.value) : fmtInt(it.value)}</b>}
        </span>
      ))}
    </div>
  );
}

export function ChartCard({ title, subtitle, icon, children, height = 280, loading }) {
  return (
    <section className="card">
      <div className="card-title">
        {icon && <Icon name={icon} size={20} />}
        <h2>{title}</h2>
      </div>
      {subtitle && <div className="card-sub">{subtitle}</div>}
      <div style={{ height }} aria-busy={loading || undefined}>
        {loading ? <Skeleton height={height} label={`Chargement : ${title}`} /> : children}
      </div>
    </section>
  );
}

// Dégradé « du plus bas au plus haut » pour une clé de valeurs ordonnées
export function GradientKey({ low, high }) {
  return (
    <div className="chart-key" aria-label={`Légende : de ${low} à ${high}`}>
      <span>{low}</span>
      <span aria-hidden style={{ display: "inline-flex", gap: 2 }}>
        {[1, 2, 3, 4, 5].map((n) => <i key={n} style={{ width: 18, height: 10, borderRadius: 2, background: `var(--seq-${n})` }} />)}
      </span>
      <span>{high}</span>
    </div>
  );
}

// Clé limitée aux catégories présentes dans les données, dans l'ordre d'apparition
export function categoryKey(rows, field, dimension) {
  const seen = [];
  rows?.forEach((r, i) => {
    const cat = r[field] || "Autres";
    if (!seen.some((s) => s.label === cat)) seen.push({ label: cat, color: colorFor(dimension, cat, i) });
  });
  return seen;
}

// Barres horizontales. Couleur : `dimension` (une couleur par entité), `colorOf(row, i)` (règle libre)
// ou bleu par défaut. Une clé s'affiche dès qu'il y a plusieurs couleurs (`keyItems` pour la personnaliser).
export function HBar({ data, x = "jobs", y = "label", unit, formatter, color = PRIMARY, onClick, dimension, colorOf, keyItems }) {
  const rows = sortByOrder(data, dimension, y);
  const fill = (r, i) => (colorOf ? colorOf(r, i) : dimension ? colorFor(dimension, r[y], i) : color);
  return (
    <div className="chart-stack">
      <div className="chart-area">
        <ResponsiveContainer>
          <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 24 }} barCategoryGap={4}>
            <CartesianGrid horizontal={false} stroke="var(--g150)" />
            <XAxis type="number" {...axis} tickFormatter={formatter} />
            <YAxis type="category" dataKey={y} width={150} {...axis} tickFormatter={label} interval={0} />
            <Tooltip content={<Tip unit={unit} formatter={formatter} />} cursor={{ fill: "var(--g100)" }} />
            <Bar dataKey={x} radius={[0, 4, 4, 0]} maxBarSize={18} onClick={onClick} style={{ cursor: onClick ? "pointer" : "default" }}>
              {rows?.map((r, i) => <Cell key={r[y]} fill={fill(r, i)} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {keyItems ? <Key items={keyItems} formatter={formatter} />
        : dimension && <Key items={rows.map((r, i) => ({ label: r[y], color: fill(r, i), value: r[x] }))} formatter={formatter} />}
    </div>
  );
}

export function VBar({ data, x = "label", y = "jobs", unit, formatter, dimension, colorOf, keyNode }) {
  const rows = sortByOrder(data, dimension, x);
  const fill = (r, i) => (colorOf ? colorOf(r, i) : dimension ? colorFor(dimension, r[x], i) : PRIMARY);
  const tilted = rows?.length > 6;
  return (
    <div className="chart-stack">
      <div className="chart-area">
        <ResponsiveContainer>
          <BarChart data={rows} margin={{ top: 8, right: 8 }}>
            <CartesianGrid vertical={false} stroke="var(--g150)" />
            <XAxis dataKey={x} {...axis} tickFormatter={label} interval={0} angle={tilted ? -25 : 0} textAnchor={tilted ? "end" : "middle"} height={tilted ? 60 : 30} />
            <YAxis {...axis} tickFormatter={formatter} width={60} />
            <Tooltip content={<Tip unit={unit} formatter={formatter} />} cursor={{ fill: "var(--g100)" }} />
            <Bar dataKey={y} radius={[4, 4, 0, 0]} maxBarSize={36}>
              {rows?.map((r, i) => <Cell key={r[x]} fill={fill(r, i)} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {keyNode || (dimension && <Key items={rows.map((r, i) => ({ label: r[x], color: fill(r, i), value: r[y] }))} formatter={formatter} />)}
    </div>
  );
}

// Aires empilées : une couleur par source (même code couleur que partout), clé avec le total de chaque source
export function StackedArea({ data, keys, totals, dimension = "source", x = "period" }) {
  return (
    <div className="chart-stack">
      <div className="chart-area">
        <ResponsiveContainer>
          <AreaChart data={data} margin={{ top: 8, right: 12 }}>
            <CartesianGrid vertical={false} stroke="var(--g150)" />
            <XAxis dataKey={x} {...axis} minTickGap={24} />
            <YAxis {...axis} width={44} allowDecimals={false} />
            <Tooltip content={<Tip />} cursor={{ stroke: "var(--g300)", strokeDasharray: "3 3" }} />
            {keys.map((k, i) => (
              <Area key={k} type="monotone" dataKey={k} name={label(k)} stackId="all" stroke={colorFor(dimension, k, i)}
                fill={colorFor(dimension, k, i)} fillOpacity={0.35} strokeWidth={1.5} />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <Key items={keys.map((k, i) => ({ label: k, color: colorFor(dimension, k, i), value: totals?.[k] }))} />
    </div>
  );
}

export function TimeArea({ data, x = "period", y = "jobs" }) {
  return (
    <ResponsiveContainer>
      <AreaChart data={data} margin={{ top: 8, right: 12 }}>
        <defs>
          <linearGradient id="fillArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--red)" stopOpacity={0.25} />
            <stop offset="100%" stopColor="var(--red)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="var(--g150)" />
        <XAxis dataKey={x} {...axis} minTickGap={24} />
        <YAxis {...axis} width={44} allowDecimals={false} />
        <Tooltip content={<Tip />} cursor={{ stroke: "var(--g300)", strokeDasharray: "3 3" }} />
        <Area type="monotone" dataKey={y} stroke="var(--red)" strokeWidth={2} fill="url(#fillArea)" activeDot={{ r: 5 }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function MultiLine({ data, keys, x = "period" }) {
  return (
    <ResponsiveContainer>
      <LineChart data={data} margin={{ top: 8, right: 12 }}>
        <CartesianGrid vertical={false} stroke="var(--g150)" />
        <XAxis dataKey={x} {...axis} minTickGap={24} />
        <YAxis {...axis} width={40} allowDecimals={false} />
        <Tooltip content={<Tip />} cursor={{ stroke: "var(--g300)", strokeDasharray: "3 3" }} />
        <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
        {keys.map((k, i) => (
          <Line key={k} dataKey={k} name={k} stroke={CATEGORICAL[i % CATEGORICAL.length]} strokeWidth={2} dot={false} activeDot={{ r: 4 }} connectNulls />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

// Donut avec clé obligatoire ; au-delà de 6 catégories, regroupement en « Autres » (gris)
export function Donut({ data, total, dimension }) {
  const top = data.slice(0, 6);
  const rest = data.slice(6).reduce((s, d) => s + d.jobs, 0);
  const rows = rest ? [...top, { label: "Autres", jobs: rest }] : top;
  const sum = rows.reduce((s, d) => s + d.jobs, 0) || 1;
  const color = (r, i) => colorFor(dimension, r.label, i);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(140px, 1fr) minmax(0, 1.2fr)", alignItems: "center", height: "100%" }}>
      <ResponsiveContainer>
        <PieChart>
          <Pie data={rows} dataKey="jobs" nameKey="label" innerRadius="62%" outerRadius="92%" stroke="var(--w)" strokeWidth={2}>
            {rows.map((r, i) => <Cell key={r.label} fill={color(r, i)} />)}
          </Pie>
          <Tooltip content={<Tip />} />
          {total !== undefined && (
            <text x="50%" y="50%" textAnchor="middle" dominantBaseline="middle" fill="var(--g900)" fontWeight="800" fontSize="18">{fmtInt(total)}</text>
          )}
        </PieChart>
      </ResponsiveContainer>
      <div className="legend" style={{ flexDirection: "column" }} role="list" aria-label="Légende">
        {rows.map((r, i) => (
          <div key={r.label} role="listitem" style={{ display: "flex", justifyContent: "space-between", gap: 8, minWidth: 0 }}>
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}><i style={{ background: color(r, i) }} />{label(r.label)}</span>
            <b>{Math.round((100 * r.jobs) / sum)} %</b>
          </div>
        ))}
      </div>
    </div>
  );
}

// Squelette à la place du contenu attendu : l'attente se voit, sans sembler bloquée
export function Skeleton({ height = 120, lines, label: aria = "Chargement" }) {
  if (lines) {
    return (
      <div className="skeleton-stack" aria-busy="true" aria-label={aria}>
        {Array.from({ length: lines }, (_, i) => <div key={i} className="skeleton" style={{ height: 14, width: `${90 - i * 12}%` }} />)}
      </div>
    );
  }
  return <div className="skeleton" style={{ height }} aria-busy="true" aria-label={aria} />;
}

export function State({ loading, error, empty }) {
  if (loading) return <Skeleton lines={3} />;
  if (error) return <Alert kind="error">{error}</Alert>;
  if (empty) return <Alert kind="info" dismissible={false}>Pas encore de données. Lancez le pipeline (DAG jobinsight_pipeline dans Airflow).</Alert>;
  return null;
}
