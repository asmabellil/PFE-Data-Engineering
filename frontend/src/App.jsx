import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, FilterProvider, useAuth } from "./context";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Jobs from "./pages/Jobs";
import Analyses from "./pages/Analyses";
import Skills from "./pages/Skills";
import AI from "./pages/AI";
import Pipeline from "./pages/Pipeline";

function Protected({ children, role }) {
  const { user, ready } = useAuth();
  if (!ready) return <div className="center muted">Chargement…</div>;
  if (!user) return <Navigate to="/login" replace />;
  const order = ["viewer", "analyst", "admin"];
  if (role && order.indexOf(user.role) < order.indexOf(role))
    return <div className="card">Accès réservé au rôle « {role} ».</div>;
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <FilterProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Protected><Layout /></Protected>}>
            <Route index element={<Dashboard />} />
            <Route path="offres" element={<Jobs />} />
            <Route path="analyses" element={<Analyses />} />
            <Route path="competences" element={<Skills />} />
            <Route path="ia" element={<AI />} />
            <Route path="pipeline" element={<Protected role="analyst"><Pipeline /></Protected>} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </FilterProvider>
    </AuthProvider>
  );
}
