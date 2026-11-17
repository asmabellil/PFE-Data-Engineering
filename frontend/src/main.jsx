import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
// polices hébergées avec l'application : aucun appel à un service externe (RGPD, politique de sécurité du site)
import "@fontsource-variable/plus-jakarta-sans";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/600.css";
import App from "./App.jsx";
import "./styles.css";
import "./dark.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
