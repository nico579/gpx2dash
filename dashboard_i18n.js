/* Explicit UI translations: track names, city names and other user data are never translated. */
const dashboardI18n = (() => {
 "use strict";
 const data = JSON.parse(document.getElementById("dashboard-data").textContent);
 const english = {
  "GPX2DASH · Mes itinéraires": "GPX2DASH · My routes",
  "Langue": "Language",
  "Traces GPX · Tableau de bord": "GPX tracks · Dashboard",
  "Tableau de bord des traces": "Track dashboard",
  "Une trace par ligne, pour comparer les sorties et préparer le trajet.": "One track per row, to compare outings and plan the drive.",
  "Départ des trajets": "Driving origin",
  "Traces du catalogue": "Tracks in catalogue",
  "Distance cumulée des traces": "Total track distance",
  "Dénivelé positif connu": "Known elevation gain",
  "Trajets routiers OSRM renseignés": "Known OSRM driving routes",
  "Choisir la ville de départ des trajets": "Choose the driving origin",
  "Ville à rechercher": "Search for a town",
  "Ex. Toulon, France": "e.g. Toulon, France",
  "Rechercher": "Search",
  "Ville retenue": "Selected town",
  "Choisir la ville trouvée": "Choose a matching town",
  "Calculer les trajets": "Calculate routes",
  "Recherchez une ville, sélectionnez-la, puis calculez les trajets. Connexion Internet nécessaire.": "Search for a town, select it, then calculate routes. Internet connection required.",
  "Annuler": "Cancel",
  "Toutes les traces": "All tracks",
  "Carte du KML agrégé": "Aggregated KML map",
  "KML agrégé": "Aggregated KML",
  "Couleurs du KML": "KML colours",
  "Traces filtrées uniquement": "Filtered tracks only",
  "Télécharger le KML complet": "Download complete KML",
  "Carte interactive des traces du KML agrégé": "Interactive map of the aggregated KML tracks",
  "{n} / {total} trace(s) affichée(s). Cliquez sur une trace pour voir ses informations.": "{n} / {total} track(s) displayed. Click a track to see its details.",
  "Aucune trace géolocalisée ne correspond aux filtres.": "No mapped tracks match the filters.",
  "Parcours regroupés dans le KML": "Tracks grouped in the KML",
  "Voir l’itinéraire et la trace": "View driving route and track",
  "Détails de la trace : {name}": "Track details: {name}",
  "Rechercher une trace, un lieu ou une date": "Search for a track, place or date",
  "Rechercher une trace, un lieu, une date…": "Search for a track, place, date…",
  "Effacer les filtres": "Clear filters",
  "Tableau des traces, défilement horizontal sur petit écran": "Track table, scroll vertically and horizontally",
  "Cliquez sur un en-tête pour trier. Les valeurs non renseignées sont indiquées par un tiret.": "Click a column header to sort. Missing values are shown as a dash.",
  "Date / trace": "Date / track",
  "Date": "Date",
  "Lieu de départ": "Starting place",
  "Distance de la trace": "Track distance",
  "Dénivelé D+ / D−": "Elevation gain / loss",
  "Dénivelé D+": "Elevation gain",
  "Durée de la trace": "Track duration",
  "Distance de route": "Driving distance",
  "Durée de route": "Driving time",
  "Goudron longé (OSM)": "Alongside asphalt (OSM)",
  "Aucune trace à afficher.": "No tracks to display.",
  "Trajets depuis": "Routes from",
  "Routage": "Routing",
  "Villes": "Towns",
  "contributeurs OpenStreetMap": "OpenStreetMap contributors",
  "Corriger la carte": "Improve the map",
  "Itinéraire et trace GPX": "Driving route and GPX track",
  "Itinéraire OpenStreetMap ↗": "OpenStreetMap directions ↗",
  "Fermer": "Close",
  "Légende de la carte": "Map legend",
  "Trajet routier": "Driving route",
  "Trace GPX": "GPX track",
  "Vue d’ensemble": "Overview",
  "Zoom sur la trace": "Zoom to track",
  "Carte interactive du trajet routier et de la trace GPX": "Interactive driving route and GPX track map",
  "Fond de carte indisponible. Les tracés restent visibles ; vérifiez votre connexion Internet.": "Map tiles unavailable. The routes remain visible; check your Internet connection.",
  "Télécharger le GPX original": "Download original GPX",
  "Ouvrir le trajet dans OpenStreetMap ↗": "Open directions in OpenStreetMap ↗",
  "Bilan des traces": "Track overview",
  "Date inconnue": "Unknown date",
  "Lieu inconnu": "Unknown place",
  "Trace illisible": "Unreadable track",
  "Dénivelé inconnu": "Unknown elevation",
  "Tous": "All",
  "Entre (inclus)": "Between",
  "Commune": "Town",
  "Opérateur pour {name}": "Operator for {name}",
  "{name} : {bound}{unit}": "{name}: {bound}{unit}",
  "borne basse": "lower bound",
  "borne haute": "upper bound",
  "valeur": "value",
  "Nombre invalide.": "Invalid number.",
  "Date invalide.": "Invalid date.",
  "Bornes inversées.": "Reversed bounds.",
  "Aucun filtre de colonne.": "No column filters.",
  "{n} condition(s) active(s).": "{n} active condition(s).",
  "{n} condition(s) à compléter (non appliquées).": "{n} incomplete condition(s) (not applied).",
  "{n} condition(s) invalide(s) (non appliquées).": "{n} invalid condition(s) (not applied).",
  "{visible} / {total} trace(s)": "{visible} / {total} track(s)",
  "{km} incertains": "{km} uncertain",
  "Trajet non renseigné.": "Route unavailable.",
  "OSRM, relevé le {date}. Sans trafic en temps réel.": "OSRM, retrieved {date}. No live traffic.",
  "routeNote": "One-way driving routes from OSRM, without live traffic, to the nearest accessible road at the track start. Walking access is excluded. {missing} route(s) unavailable; hover over the cells for details. {errors} unreadable GPX file(s).",
  "Généré le {date} · GPX2DASH": "Generated {date} · GPX2DASH",
  "Calcul annulé.": "Calculation cancelled.",
  "Service occupé (HTTP 429). Patientez quelques instants, puis relancez le calcul.": "Service busy (HTTP 429). Wait a little before trying again.",
  "Service indisponible (HTTP {code}).": "Service unavailable (HTTP {code}).",
  "Requête refusée.": "Request rejected.",
  "Délai du service dépassé. Réessayez.": "Service timeout. Try again.",
  "Connexion au service impossible. Vérifiez votre accès Internet.": "Cannot connect to the service. Check your Internet connection.",
  "Recherche de la ville…": "Searching for town…",
  "Réponse de recherche incomplète.": "Incomplete town search response.",
  "Sélectionnez la ville, puis cliquez sur « Calculer les trajets ».": "Select the town, then click “Calculate routes”.",
  "Aucune ville trouvée. Précisez le département ou le pays.": "No town found. Specify the region or country.",
  "Cliquez sur « Rechercher » pour trouver la ville.": "Click “Search” to find the town.",
  "OSRM : aucun point routier ou itinéraire trouvé.": "OSRM: no road point or route found.",
  "OSRM : réponse incomplète.": "OSRM: incomplete response.",
  "La ville de départ est à plus de 1 km du réseau routier.": "The origin town is more than 1 km from the road network.",
  "Aucune liaison routière depuis la ville de départ.": "No road connection from the origin town.",
  "OSRM : distance ou durée invalide.": "OSRM: invalid distance or duration.",
  "Aucune liaison routière trouvée à proximité du départ de la trace (rayon de 1 km).": "No road connection near the track start (1 km radius).",
  "Calcul depuis {city} : {n} / {total} traces traitées…": "Calculating from {city}: {n} / {total} tracks processed…",
  "{n} trajets renseignés depuis {city}. {missing} non renseignés.": "{n} routes available from {city}. {missing} unavailable.",
  "{error} Les valeurs affichées correspondent à {city}. Les lots terminés sont conservés pour reprendre.": "{error} Displayed values correspond to {city}. Completed batches are saved for resuming.",
  "Dernier départ restauré : {city}. Résultats repris du cache.": "Last origin restored: {city}. Results loaded from cache.",
  "Aucun itinéraire routier trouvé depuis cette ville.": "No driving route found from this town.",
  "Réponse routière incomplète.": "Incomplete driving route response.",
  "Aucune liaison routière trouvée à proximité des points de départ (rayon de 1 km).": "No road connection near the starting points (1 km radius).",
  "Trajet aller depuis {city}": "One-way drive from {city}",
  "Trace GPX affichée. Chargement de l’itinéraire routier…": "GPX track displayed. Loading driving route…",
  "Départ routier : {city}": "Driving origin: {city}",
  "Départ de la trace GPX": "GPX track start",
  "Trajet routier : {distance} · {duration}. Trace GPX affichée en orange.": "Driving route: {distance} · {duration}. GPX track shown in orange.",
  "{error} La trace GPX reste affichée.": "{error} The GPX track remains visible.",
  "Carte indisponible : {error}": "Map unavailable: {error}",
  "asphaltTitle": "OSM bituminous road axes within {margin} m, direction difference ≤ {angle}°. Explicit asphalt, chipseal, tarmac, bitumen or tar only. Missing or ambiguous surfaces are uncertain. The filter uses the confirmed minimum. {date}",
  "Données OSM du {date}.": "OSM data from {date}.",
  "Routage désactivé, valeur absente du cache.": "Routing disabled; value missing from cache.",
  "Mesure du goudron absente du cache. Relancez avec --goudron.": "Asphalt measurement missing from cache. Run again with --asphalt.",
  "Trajet absent du cache hors connexion.": "Route missing from the offline cache.",
  "Goudron non calculé : lancer gpx2dash.py avec --asphalt (Internet requis).": "Asphalt not calculated: run gpx2dash with --asphalt (Internet required).",
  "GPX original ou empreinte absente ; goudron non calculé.": "Original GPX or fingerprint missing; asphalt not calculated.",
  "Le GPX a changé pendant le calcul ; régénérez le tableau.": "The GPX changed during calculation; regenerate the dashboard.",
  "Service de recherche de villes indisponible.": "Town search service unavailable."
};
 const reverse = new Map(Object.entries(english).map(([fr, en]) => [en, fr]));
 const french = {
  "routeNote": "Trajets aller en voiture calculés par OSRM, sans trafic en temps réel, jusqu’à la route accessible la plus proche du départ. L’approche à pied n’est pas incluse. {missing} trajet(s) non renseigné(s) ; la raison apparaît au survol des cellules. {errors} fichier(s) GPX illisible(s).",
  "asphaltTitle": "Voies OSM bitumineuses longées à {margin} m maximum ; écart de direction ≤ {angle}°. Asphalt, chipseal, tarmac, bitumen ou tar uniquement. Les revêtements absents ou ambigus restent incertains. Le filtre porte sur le minimum repéré. {date}",
  "Entre (inclus)": "Entre"
};
 const html = {
  "filterHelp": [
    "<strong>Toutes les conditions se combinent (ET).</strong> « Entre » inclut les bornes.<br>Distances : km · D+ : m · Durées : minutes · Lieux : ordre alphabétique.",
    "<strong>All conditions are combined (AND).</strong> “Between” includes both bounds.<br>Distances: km · Elevation gain: m · Durations: minutes · Places: alphabetical order."
  ],
  "trackNote": [
    "<strong>Lecture des traces.</strong> La durée estime le temps en mouvement, avec repli sur le temps écoulé. Le dénivelé est une estimation du moteur gpx2elev. Le lieu correspond à la commune la plus proche ; le lien OpenStreetMap utilise les coordonnées du départ.",
    "<strong>Reading tracks.</strong> Duration estimates moving time, falling back to elapsed time. Elevation gain is estimated by gpx2elev. The place is the nearest town; the OpenStreetMap link uses the starting coordinates."
  ],
  "surfaceNote": [
    "<strong>Goudron longé.</strong> Estimation sur le GPX d’origine, à moins de {margin} m de l’axe d’une voie bitumineuse OSM et avec un écart de direction de {angle}° maximum ; les croisements perpendiculaires sont exclus. Échantillonnage de 5 m. « ≥ » indique le minimum repéré si le revêtement reste incertain ; un tiret indique un calcul absent ou aucune portion confirmée malgré des revêtements incertains. Les filtres portent sur la distance repérée. <a href=\"https://wiki.openstreetmap.org/wiki/Key:surface\" target=\"_blank\" rel=\"noopener noreferrer\">Revêtements OpenStreetMap</a>.",
    "<strong>Alongside asphalt.</strong> Estimated on the original GPX, within {margin} m of an OSM bituminous road axis and a maximum direction difference of {angle}°; perpendicular crossings are excluded. Sampled every 5 m. “≥” is the confirmed minimum when some surfaces are uncertain; a dash means no calculation or no confirmed portion with uncertain surfaces. Filters use the confirmed distance. <a href=\"https://wiki.openstreetmap.org/wiki/Key:surface\" target=\"_blank\" rel=\"noopener noreferrer\">OpenStreetMap surfaces</a>."
  ]
};
 let saved;
 try { saved = localStorage.getItem("gpx2dash.language.v1"); } catch { /* memory-only preference */ }
 let language = ["en", "fr"].includes(saved) ? saved : data.language || (navigator.language.startsWith("fr") ? "fr" : "en");
 const bindings = new Map();
 const t = (key, values = {}) => {
  key = reverse.get(key) || key;
  let template = (language === "en" ? english[key] : french[key]) || key;
  if (language === "fr" && key === "{n} condition(s) active(s).")
   template = values.n + (values.n > 1 ? " conditions actives." : " condition active.");
  return template.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));
 };
 function text(element, key, values = {}) {
  bindings.set(element, {key, values});
  element.textContent = t(key, typeof values === "function" ? values() : values);
 }
 function apply() {
  document.documentElement.lang = language;
  document.getElementById("language").value = language;
  document.querySelectorAll("[data-i18n]").forEach(el => el.textContent = t(el.dataset.i18n));
  for (const attr of ["aria-label", "placeholder"])
   document.querySelectorAll("[data-i18n-" + attr + "]").forEach(el => el.setAttribute(attr, t(el.getAttribute("data-i18n-" + attr))));
  document.querySelectorAll("[data-i18n-html]").forEach(el => {
   // Templates contain only project markup and numeric protocol parameters.
   el.innerHTML = html[el.dataset.i18nHtml][language === "fr" ? 0 : 1]
    .replace("{margin}", String(data.asphaltTolerance)).replace("{angle}", String(data.asphaltAngle));
  });
  bindings.forEach(({key, values}, el) => el.textContent = t(key, typeof values === "function" ? values() : values));
 }
 document.getElementById("language").addEventListener("change", event => {
  language = event.target.value;
  try { localStorage.setItem("gpx2dash.language.v1", language); } catch { /* memory-only preference */ }
  apply();
  document.dispatchEvent(new Event("dashboard-language"));
 });
 apply();
 return {t, text, get language() {return language;}, get locale() {return language === "fr" ? "fr-FR" : "en-GB";}};
})();
