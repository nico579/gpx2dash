/* Tableau autonome : tri, filtres combinés, recherche Photon et matrices OSRM sur demande. */
(() => {
 "use strict";
 const {t, text: message} = dashboardI18n;
 const data = JSON.parse(document.getElementById("dashboard-data").textContent);
 const table = document.getElementById("traces"), body = table.tBodies[0];
 const rows = Array.from(body.rows), headers = Array.from(table.tHead.rows[0].cells);
 const rowById = new Map(rows.map(row => [row.dataset.id, row]));
 const count = document.getElementById("visible-count"), empty = document.getElementById("no-results");
 const form = document.getElementById("city-form"), input = document.getElementById("route-city");
 const select = document.getElementById("city-results"), searchButton = document.getElementById("city-search");
 const calculateButton = document.getElementById("calculate-routes"), cancelButton = document.getElementById("cancel-routes");
 const status = document.getElementById("route-status");
 const normalise = text => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("fr");
 const searchTexts = new Map();
 const searchInput = document.getElementById("search");
 const resetFilters = document.getElementById("reset-filters");
 const filtersStatus = document.getElementById("filters-status");
 const filterSpecs = [
  {name: "Date", type: "date"},
  {name: "Lieu de départ", type: "text", placeholder: "Commune"},
  {name: "Distance de la trace", type: "number", unit: "km"},
  {name: "Dénivelé D+", type: "number", unit: "m"},
  {name: "Durée de la trace", type: "number", unit: "min"},
  {name: "Distance de route", type: "number", unit: "km"},
  {name: "Durée de route", type: "number", unit: "min"},
   {name: "Goudron longé (OSM)", type: "number", unit: "km"},
   {name: "Traces communes", type: "number", unit: "traces"}
 ];
 const filterControls = filterSpecs.map((spec, index) => {
  const cell = document.getElementById("column-filters").insertCell();
  cell.className = "column-filter";
  const operator = document.createElement("select");
  operator.id = "filter-" + index + "-op";
  operator.setAttribute("aria-label", t("Opérateur pour {name}", {name: t(spec.name)}));
  operator.setAttribute("aria-describedby", "filter-help");
  for (const [value, label] of [["", t("Tous")], ["=", "="], [">", ">"], ["<", "<"], ["between", t("Entre (inclus)")]]) {
   const option = document.createElement("option");
   option.value = value; option.textContent = label; operator.appendChild(option);
  }
  const makeInput = suffix => {
   const field = document.createElement("input");
   field.id = "filter-" + index + "-" + suffix;
   field.type = spec.type === "date" ? "date" : "text";
   if (spec.type === "number") field.inputMode = "decimal";
   if (spec.type === "date") { field.min = "0001-01-01"; field.max = "9999-12-31"; }
   field.autocomplete = "off";
   field.setAttribute("aria-describedby", "filter-help filter-" + index + "-error");
   field.addEventListener("input", filter);
   return field;
  };
  const first = makeInput("value"), second = makeInput("upper");
  const error = document.createElement("span");
  error.id = "filter-" + index + "-error"; error.className = "filter-error"; error.hidden = true;
  cell.append(operator, first, second, error);
  const control = {...spec, index, operator, first, second, error};
  operator.addEventListener("change", () => { updateFilterInputs(control); filter(); });
  updateFilterInputs(control);
  return control;
 });
 function updateFilterInputs(control) {
  const between = control.operator.value === "between", inactive = !control.operator.value;
  const name = t(control.name);
  control.operator.setAttribute("aria-label", t("Opérateur pour {name}", {name}));
  control.operator.options[0].textContent = t("Tous");
  control.operator.options[4].textContent = t("Entre (inclus)");
  const unit = control.unit ? " (" + control.unit + ")" : "";
  control.first.disabled = inactive;
  control.second.disabled = !between; control.second.hidden = !between;
  control.first.setAttribute("aria-label", t("{name} : {bound}{unit}", {name, bound: t(between ? "borne basse" : "valeur"), unit}));
  control.second.setAttribute("aria-label", t("{name} : {bound}{unit}", {name, bound: t("borne haute"), unit}));
  control.first.placeholder = (between ? "Min · " : "") + (control.unit || t(control.placeholder || ""));
  control.second.placeholder = "Max · " + (control.unit || t(control.placeholder || ""));
 }
 function readFilterValue(field, control) {
  const value = field.value.trim();
  if (!value) return {missing: true};
  if (control.type === "number") {
   const number = value.replace(/\s/g, "").replace(",", ".");
   if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(number) || !Number.isFinite(Number(number)))
    return {error: t("Nombre invalide.")};
   return {value: Number(number)};
  }
  if (control.type === "date") {
   if (!field.validity.valid || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return {error: t("Date invalide.")};
   return {value};
  }
  return {value: normalise(value.replace(/\s+/g, " "))};
 }
 function compareValues(a, b, index) {
  return index < 2 ? a.localeCompare(b, dashboardI18n.locale) : a - b;
 }
 function filterError(control, message, fields) {
  control.error.textContent = message; control.error.hidden = false;
  fields.forEach(field => { field.setCustomValidity(message); field.setAttribute("aria-invalid", "true"); });
 }
 function compileFilters() {
  const conditions = [];
  let pending = 0, invalid = 0;
  filterControls.forEach(control => {
   const {operator, first, second, index} = control;
   control.error.hidden = true;
   [first, second].forEach(field => { field.setCustomValidity(""); field.removeAttribute("aria-invalid"); });
   if (!operator.value) return;
   const fields = operator.value === "between" ? [first, second] : [first];
   const values = fields.map(field => readFilterValue(field, control));
   if (values.some(value => value.error)) {
    values.forEach((value, i) => { if (value.error) filterError(control, value.error, [fields[i]]); });
    invalid++; return;
   }
   if (values.some(value => value.missing)) { pending++; return; }
   if (operator.value === "between" && compareValues(values[0].value, values[1].value, index) > 0) {
    filterError(control, t("Bornes inversées."), fields); invalid++; return;
   }
   conditions.push({index, operator: operator.value, lower: values[0].value, upper: values[1]?.value});
  });
  const messages = [conditions.length ? t("{n} condition(s) active(s).", {n: conditions.length}) : t("Aucun filtre de colonne.")];
  if (pending) messages.push(t("{n} condition(s) à compléter (non appliquées).", {n: pending}));
  if (invalid) messages.push(t("{n} condition(s) invalide(s) (non appliquées).", {n: invalid}));
  filtersStatus.textContent = messages.join(" ");
  resetFilters.disabled = !searchInput.value && !filterControls.some(control => control.operator.value || control.first.value || control.second.value);
  return conditions;
 }
 function matchesCondition(row, condition) {
  const {index, operator, lower, upper} = condition, raw = row.cells[index].dataset.filter;
  if (raw === undefined || !raw.trim()) return false;
  const value = index < 2 ? normalise(raw.trim().replace(/\s+/g, " ")) : Number(raw);
  if (index >= 2 && !Number.isFinite(value)) return false;
  const comparison = compareValues(value, lower, index);
  if (operator === "=") return comparison === 0;
  if (operator === ">") return comparison > 0;
  if (operator === "<") return comparison < 0;
  return comparison >= 0 && compareValues(value, upper, index) <= 0;
 }

 const validPosition = p => Array.isArray(p) && p.length === 2 &&
  p.every(v => typeof v === "number" && Number.isFinite(v)) && Math.abs(p[0]) <= 90 && Math.abs(p[1]) <= 180;
 const coordinate = p => p.map(v => v.toFixed(6)).join(",");
 const key = (position, origin) => data.serveur + "|" + coordinate(origin) + "|" + coordinate(position);
 const known = v => typeof v === "number" && Number.isFinite(v) && v >= 0;
 const distance = v => known(v) ? (v / 1000).toFixed(1).replace(".", dashboardI18n.language === "fr" ? "," : ".") + " km" : "—";
 const duration = v => {
  if (!known(v)) return "—";
  const minutes = Math.round(v / 60), h = Math.floor(minutes / 60), m = minutes % 60;
  return h ? h + " h " + String(m).padStart(2, "0") : m + " min";
 };
 let column = 0, ascending = false, origin = data.origine, choices = [data.origine], controller = null;
 let lastRequest = -Infinity;
 let requestQueue = Promise.resolve();
 const routeCache = new Map(), cityCache = new Map();
 let currentRoutes = null;
 function readStorage(name, fallback) {
  try { return JSON.parse(localStorage.getItem(name)) || fallback; } catch { return fallback; }
 }
 function writeStorage(name, value) {
  try { localStorage.setItem(name, JSON.stringify(value)); } catch { /* cache mémoire si stockage interdit ou plein */ }
 }
 // Pas d'expiration : un trajet, ou une erreur durable, reste valable.
 function usable(route) {
  if (!route || typeof route !== "object" || Number.isNaN(Date.parse(route.date_route))) return false;
  return route.erreur_route ? route.route_cacheable === true : known(route.distance_route_m) && known(route.duree_route_s);
 }
 for (const entries of [readStorage("gpx2dash.routes.v1", {}), data.cache]) {
  for (const [k, route] of Object.entries(entries)) {
   if (usable(route) && (!routeCache.has(k) ||
    Date.parse(route.date_route) > Date.parse(routeCache.get(k).date_route))) routeCache.set(k, route);
  }
 }
 function saveCache() {
  for (const [k, route] of routeCache) if (!usable(route)) routeCache.delete(k);
  writeStorage("gpx2dash.routes.v1", Object.fromEntries(routeCache));
 }
 function filter() {
  const words = normalise(searchInput.value).trim().split(/\s+/).filter(Boolean);
  const conditions = compileFilters();
  let visible = 0;
  rows.forEach(row => {
   row.hidden = !words.every(word => searchTexts.get(row).includes(word)) ||
    !conditions.every(condition => matchesCondition(row, condition));
   if (!row.hidden) visible++;
  });
  count.textContent = t("{visible} / {total} trace(s)", {visible, total: rows.length});
  empty.hidden = visible !== 0;
  table.dispatchEvent(new Event("dashboard-filter"));
 }
 function refreshSearch() {
  rows.forEach(row => searchTexts.set(row, normalise(row.textContent)));
  filter();
 }
 function sort() {
  rows.sort((a, b) => {
   const av = a.cells[column].dataset.sort, bv = b.cells[column].dataset.sort;
   if (av === "") return bv === "" ? 0 : 1;
   if (bv === "") return -1;
   return (ascending ? 1 : -1) * (column >= 2 ? Number(av) - Number(bv) : av.localeCompare(bv, dashboardI18n.locale));
  });
  rows.forEach(row => body.appendChild(row));
  headers.forEach((h, i) => h.setAttribute("aria-sort", i === column ? (ascending ? "ascending" : "descending") : "none"));
 }
 headers.forEach((header, index) => header.querySelector("button").addEventListener("click", () => {
  ascending = index === column ? !ascending : true;
  column = index;
  sort();
 }));
 searchInput.addEventListener("input", filter);
 resetFilters.addEventListener("click", () => {
  searchInput.value = "";
  filterControls.forEach(control => {
   control.operator.value = ""; control.first.value = ""; control.second.value = "";
   updateFilterInputs(control);
  });
  filter();
 });
 function setChoices(values) {
  choices = values;
  select.replaceChildren();
  values.forEach((city, index) => {
   const option = document.createElement("option");
   option.value = String(index); option.textContent = city.libelle; select.appendChild(option);
  });
  select.disabled = !values.length;
  calculateButton.disabled = !values.length;
 }
 function setBusy(busy, calculation = false) {
  searchButton.disabled = busy; input.disabled = busy; select.disabled = busy || !choices.length;
  calculateButton.disabled = busy || !choices.length;
  cancelButton.hidden = !(busy && calculation);
  document.getElementById("route-settings").setAttribute("aria-busy", String(busy));
 }
 function osmLink(position, start) {
  return "https://www.openstreetmap.org/directions?" + new URLSearchParams({
   engine: "fossgis_osrm_car", route: coordinate(start) + ";" + coordinate(position)
  });
 }
 function applyOrigin(city, routes) {
  origin = city;
  currentRoutes = routes;
  let completed = 0;
  data.traces.forEach(trace => {
   const row = rowById.get(trace.id);
   if (!row) return;
   const route = routes.get(key(trace.position, city.position)) || {};
   const tooltip = t(route.erreur_route || "") || (route.date_route ? t("OSRM, relevé le {date}. Sans trafic en temps réel.", {date: route.date_route}) : t("Trajet non renseigné."));
   for (const [index, value, label] of [[5, route.distance_route_m, distance], [6, route.duree_route_s, duration]]) {
    row.cells[index].dataset.sort = known(value) ? String(value) : "";
    row.cells[index].dataset.filter = known(value) ?
     (index === 5 ? (value / 1000).toFixed(1) : String(Math.round(value / 60))) : "";
    row.cells[index].textContent = label(value);
    row.cells[index].title = tooltip;
   }
   const link = row.querySelector(".route-link");
   if (link) link.href = osmLink(trace.position, city.position);
   if (known(route.distance_route_m) && known(route.duree_route_s)) completed++;
  });
  document.querySelectorAll("[data-origine]").forEach(element => element.textContent = city.libelle);
  document.getElementById("routes-count").textContent = completed + " / " + data.nombre_valides;
  message(document.getElementById("route-note"), "routeNote", {missing: data.nombre_valides - completed, errors: data.errors});
  sort(); refreshSearch();
  return completed;
 }
 function abortError() { return new DOMException(t("Calcul annulé."), "AbortError"); }
 async function pause(ms, signal) {
  if (signal && signal.aborted) throw abortError();
  if (ms <= 0) return;
  await new Promise((resolve, reject) => {
   const abort = () => { clearTimeout(timer); reject(abortError()); };
   const timer = setTimeout(() => { if (signal) signal.removeEventListener("abort", abort); resolve(); }, ms);
   if (signal) signal.addEventListener("abort", abort, {once: true});
  });
 }
 function request(url, signal) {
  const result = requestQueue.then(() => performRequest(url, signal));
  requestQueue = result.catch(() => {});
  return result;
 }
 async function performRequest(url, signal) {
  await pause(Math.max(0, 1050 - (performance.now() - lastRequest)), signal);
  if (signal && signal.aborted) throw abortError();
  lastRequest = performance.now();
  const timeout = new AbortController();
  const abort = () => timeout.abort();
  if (signal) signal.addEventListener("abort", abort, {once: true});
  const timer = setTimeout(() => timeout.abort(), 25000);
  try {
   const response = await fetch(url, {signal: timeout.signal, headers: {Accept: "application/json"}});
   if (response.status === 429) throw new Error(t("Service occupé (HTTP 429). Patientez quelques instants, puis relancez le calcul."));
   if (!response.ok && response.status !== 400) throw new Error(t("Service indisponible (HTTP {code}).", {code: response.status}));
   const result = await response.json();
   if (!response.ok && !result.code) throw new Error(t("Requête refusée."));
   return result;
  } catch (error) {
   if (signal && signal.aborted) throw abortError();
   if (error.name === "AbortError") throw new Error(t("Délai du service dépassé. Réessayez."));
   if (error instanceof TypeError) throw new Error(t("Connexion au service impossible. Vérifiez votre accès Internet."));
   throw error;
  } finally {
   clearTimeout(timer);
   if (signal) signal.removeEventListener("abort", abort);
  }
 }
 async function searchCities(event) {
  event.preventDefault();
  const query = input.value.trim();
  if (query.length < 2) return;
  setBusy(true);
  message(status, "Recherche de la ville…");
  try {
   let cities = cityCache.get(dashboardI18n.language + "|" + normalise(query));
   if (!cities) {
    const json = await request(data.geocodeur + "?" + new URLSearchParams({
     q: query, limit: "8", lang: dashboardI18n.language, osm_tag: "place"
    }));
    if (!Array.isArray(json.features)) throw new Error(t("Réponse de recherche incomplète."));
    const seen = new Set();
    cities = json.features.flatMap(feature => {
     const p = feature.properties || {}, coordinates = feature.geometry && feature.geometry.coordinates;
     if (!["city", "town", "village", "hamlet", "municipality"].includes(p.osm_value) ||
      !coordinates) return [];
     const position = [coordinates[1], coordinates[0]], id = validPosition(position) && coordinate(position);
     if (!id || seen.has(id)) return [];
     seen.add(id);
     return [{position, libelle: ["name", "postcode", "state", "country"].map(k => p[k]).filter(Boolean).join(", ")}];
    });
    cityCache.set(dashboardI18n.language + "|" + normalise(query), cities);
   }
   setChoices(cities);
   message(status, cities.length ? "Sélectionnez la ville, puis cliquez sur « Calculer les trajets »." : "Aucune ville trouvée. Précisez le département ou le pays.");
  } catch (error) {
   setChoices([]);
   message(status, error.message);
  } finally { setBusy(false); }
 }
 form.addEventListener("submit", searchCities);
 input.addEventListener("input", () => {
  setChoices([]);
  message(status, "Cliquez sur « Rechercher » pour trouver la ville.");
 });
 async function matrix(destinations, city, signal, priorityOrigin = false) {
  const positions = [city.position, ...destinations];
  // FOSSGIS répartit les requêtes par continent majoritaire dans les coordonnées.
  if (priorityOrigin) positions.push(...destinations.map(() => city.position));
  const coordinates = positions.map(p => p[1].toFixed(6) + "," + p[0].toFixed(6)).join(";");
  const json = await request(data.serveur + "/table/v1/driving/" + coordinates + "?" +
   new URLSearchParams({sources: "0", destinations: destinations.map((_, i) => i + 1).join(";"),
    annotations: "distance,duration", generate_hints: "false"}), signal);
  if (json.code !== "Ok") throw Object.assign(new Error(t("OSRM : aucun point routier ou itinéraire trouvé.")), {code: json.code});
  const distances = json.distances && json.distances[0], durations = json.durations && json.durations[0];
  const points = json.destinations, source = json.sources && json.sources[0];
  if (!Array.isArray(distances) || !Array.isArray(durations) || !Array.isArray(points) || !source ||
   [distances, durations, points].some(list => list.length !== destinations.length))
   throw new Error(t("OSRM : réponse incomplète."));
  if (source.distance > 1000 && !priorityOrigin)
   return matrix(destinations, city, signal, true);
  const timestamp = new Date().toISOString();
  return destinations.map((_, i) => {
   const route = {date_route: timestamp, route_cacheable: true};
   if (source.distance > 1000) route.erreur_route = t("La ville de départ est à plus de 1 km du réseau routier.");
   else if (distances[i] == null || durations[i] == null) route.erreur_route = t("Aucune liaison routière depuis la ville de départ.");
   else if (!known(distances[i]) || !known(durations[i])) throw new Error(t("OSRM : distance ou durée invalide."));
   else if (points[i].distance > 1000) route.erreur_route = t("Aucune liaison routière trouvée à proximité du départ de la trace (rayon de 1 km).");
   else Object.assign(route, {distance_route_m: distances[i], duree_route_s: durations[i], distance_acces_m: points[i].distance || 0});
   return route;
  });
 }
 async function resolveRoutes(destinations, city, signal) {
  try { return await matrix(destinations, city, signal); }
  catch (error) {
   if (error.code === "NoSegment" && destinations.length > 1) {
    const middle = Math.floor(destinations.length / 2);
    return [...await resolveRoutes(destinations.slice(0, middle), city, signal),
     ...await resolveRoutes(destinations.slice(middle), city, signal)];
   }
   if (["NoSegment", "NoRoute", "NoTable"].includes(error.code))
    return destinations.map(() => ({erreur_route: error.message, date_route: new Date().toISOString(), route_cacheable: true}));
   throw error;
  }
 }
 calculateButton.addEventListener("click", async () => {
  const city = choices[Number(select.value)];
  if (!city || !validPosition(city.position)) return;
  controller = new AbortController();
  setBusy(true, true);
  const groups = new Map();
  data.traces.forEach(trace => {
   const k = key(trace.position, city.position);
   if (!groups.has(k)) groups.set(k, {key: k, position: trace.position, count: 0});
   groups.get(k).count++;
  });
  const results = new Map(), missing = [];
  let finished = 0;
  groups.forEach(group => {
   if (usable(routeCache.get(group.key))) { results.set(group.key, routeCache.get(group.key)); finished += group.count; }
   else missing.push(group);
  });
  const progress = () => { message(status, "Calcul depuis {city} : {n} / {total} traces traitées…", {city: city.libelle, n: finished, total: data.traces.length}); };
  progress();
  try {
   for (let i = 0; i < missing.length; i += 25) {
    const batch = missing.slice(i, i + 25);
    const routes = await resolveRoutes(batch.map(group => group.position), city, controller.signal);
    routes.forEach((route, index) => {
     results.set(batch[index].key, route); routeCache.set(batch[index].key, route); finished += batch[index].count;
    });
    saveCache(); progress();
   }
   if (controller.signal.aborted) throw abortError();
   const completed = applyOrigin(city, results);
   writeStorage("gpx2dash.origin.v1", city);
   message(status, "{n} trajets renseignés depuis {city}. {missing} non renseignés.", {n: completed, city: city.libelle, missing: data.nombre_valides - completed});
  } catch (error) {
   message(status, "{error} Les valeurs affichées correspondent à {city}. Les lots terminés sont conservés pour reprendre.", {error: error.name === "AbortError" ? t("Calcul annulé.") : error.message, city: origin.libelle});
  } finally { controller = null; setBusy(false); }
 });
 cancelButton.addEventListener("click", () => { if (controller) controller.abort(); });
 setChoices([data.origine]);
 const saved = readStorage("gpx2dash.origin.v1", null);
 if (saved && typeof saved.libelle === "string" && validPosition(saved.position)) {
  const routes = new Map();
  data.traces.forEach(trace => {
   const k = key(trace.position, saved.position);
   if (usable(routeCache.get(k))) routes.set(k, routeCache.get(k));
  });
  // Un GPX ajouté depuis ne fait plus oublier le départ choisi : ses trajets se
  // calculent d'un clic. Sans aucun trajet en cache, le départ par défaut reste.
  const missing = data.traces.filter(trace => !routes.has(key(trace.position, saved.position))).length;
  if (routes.size) {
   applyOrigin(saved, routes); setChoices([saved]); input.value = saved.libelle;
   if (missing) message(status, "Dernier départ restauré : {city}. {n} trajet(s) à calculer : cliquez sur « Calculer les trajets ».", {city: saved.libelle, n: missing});
   else message(status, "Dernier départ restauré : {city}. Résultats repris du cache.", {city: saved.libelle});
  }
 }
 // Titres écrits par Python avec une valeur variable : le modèle se traduit, la valeur reste.
 const dynamicTitles = [
  [/^OSRM, relevé le (.*)\. Sans trafic en temps réel\.$/, "OSRM, relevé le {date}. Sans trafic en temps réel.", "date"],
  [/^OSRM : serveur indisponible \(HTTP (\d+)\)\.$/, "OSRM : serveur indisponible (HTTP {code}).", "code"],
  [/^Overpass indisponible \(HTTP (\d+)\)\. Relancez avec --asphalt pour reprendre\.$/,
   "Overpass indisponible (HTTP {code}). Relancez avec --asphalt pour reprendre.", "code"]
 ];
 function translateTitle(title) {
  for (const [pattern, template, name] of dynamicTitles) {
   const match = title.match(pattern);
   if (match) return t(template, {[name]: match[1]});
  }
  return t(title);
 }
 function cellDistance(cell) {
  return cell.dataset.filter === "" ? "—" : Number(cell.dataset.filter).toFixed(1).replace(".", dashboardI18n.language === "fr" ? "," : ".") + " km";
 }
 function renderLanguage() {
  filterControls.forEach(updateFilterInputs);
  rows.forEach(row => {
   const cells = row.cells, date = cells[0].querySelector(".date");
   if (date) date.textContent = cells[0].dataset.sort ? new Date(cells[0].dataset.sort + "T12:00:00").toLocaleDateString(dashboardI18n.locale) : t("Date inconnue");
   for (const index of [2, 4, 5, 6]) {
    const value = cells[index].dataset.sort === "" ? null : Number(cells[index].dataset.sort);
    cells[index].textContent = index === 2 || index === 5 ? cellDistance(cells[index]) : duration(value);
   }
   const value = cells[7].dataset.sort === "" ? null : Number(cells[7].dataset.sort), uncertain = Number(row.dataset.uncertain || 0);
   cells[7].textContent = (uncertain && value !== null ? "≥ " : "") + cellDistance(cells[7]);
   if (uncertain) {
    const detail = document.createElement("span"); detail.className = "detail";
    detail.textContent = t("{km} incertains", {km: distance(uncertain)}); cells[7].appendChild(detail);
   }
   // Only explicit application labels are marked. Towns, filenames and errors from GPX parsing remain verbatim.
   row.querySelectorAll("[data-row-i18n]").forEach(el => el.textContent = t(el.dataset.rowI18n));
   for (const index of [3, 5, 6, 7]) {
    const cell = cells[index]; if (!cell.dataset.originalTitle) cell.dataset.originalTitle = cell.title;
    cell.title = translateTitle(cell.dataset.originalTitle);
    if (index === 7 && !cell.dataset.error) cell.title = t("asphaltTitle", {margin: data.asphaltTolerance, angle: data.asphaltAngle, date: cell.dataset.osmDate ? t("Données OSM du {date}.", {date: cell.dataset.osmDate}) : ""});
   }
    cells[8].title = cells[8].dataset.error ? t(cells[8].dataset.error) :
     t("sharedTitle", {margin: data.overlapTolerance, minimum: data.overlapMinLength});
  });
   document.querySelector("[data-total-distance]").textContent = distance(data.totalDistance);
  document.querySelector("[data-total-ascent]").textContent = Math.round(data.totalAscent).toLocaleString(dashboardI18n.locale) + " m";
  message(document.getElementById("generated"), "Généré le {date} · GPX2DASH", () => ({date: new Date(data.generated).toLocaleString(dashboardI18n.locale, {dateStyle: "short", timeStyle: "short"})}));
  const missing = rows.filter(row => row.cells[5].dataset.sort === "" && row.cells[1].dataset.sort !== "").length;
  message(document.getElementById("route-note"), "routeNote", {missing, errors: data.errors});
  if (currentRoutes) applyOrigin(origin, currentRoutes);
  sort(); refreshSearch();
 }
 document.addEventListener("dashboard-language", renderLanguage);
 renderLanguage();
 initialiserCarteTraces({data, table, getOrigin: () => origin, request, key, distance, duration, known});
 refreshSearch();
})();
