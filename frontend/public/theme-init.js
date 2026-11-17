// Applique le thème AVANT le premier affichage : une page sombre ne doit jamais clignoter en blanc.
// Fichier externe (et non script en ligne) pour respecter la politique de sécurité du site (script-src 'self').
// Choix mémorisé de l'utilisateur en priorité, sinon réglage du système.
(function () {
  var theme = null;
  try {
    theme = localStorage.getItem("jobcompass-theme");
  } catch (e) {
    // stockage indisponible (navigation privée stricte) : on suit le système
  }
  if (theme !== "light" && theme !== "dark") {
    theme = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.style.colorScheme = theme;
})();
