// Thème clair / sombre : un seul attribut sur <html>, les composants ne changent pas (les variables CSS suivent).
const KEY = "jobcompass-theme";

export const currentTheme = () => (document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light");

export function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.style.colorScheme = theme; // barres de défilement et champs natifs
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // sans stockage, le thème change quand même : il n'est simplement pas mémorisé
  }
  // ce qui ne suit pas les variables CSS (dessins en JavaScript) peut écouter cet événement
  window.dispatchEvent(new CustomEvent("themechange", { detail: theme }));
}

export const toggleTheme = () => setTheme(currentTheme() === "dark" ? "light" : "dark");
