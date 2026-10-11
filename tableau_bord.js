/* Tableau autonome : tri, filtres combinés, recherche Photon et matrices OSRM sur demande. */
(() => {
 "use strict";
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
  {name: "Goudron longé (OSM)", type: "number", unit: "km"}
 ];
 const filterControls = filterSpecs.map((spec, index) => {
  const cell = document.getElementById("column-filters").insertCell();
  cell.className = "column-filter";
  const operator = document.createElement("select");
  operator.id = "filter-" + index + "-op";
  operator.setAttribute("aria-label", "Opérateur pour " + spec.name);
  operator.setAttribute("aria-describedby", "filter-help");
  for (const [value, label] of [["", "Tous"], ["=", "="], [">", ">"], ["<", "<"], ["between", "Entre (inclus)"]]) {
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
  const unit = control.unit ? " (" + control.unit + ")" : "";
  control.first.disabled = inactive;
  control.second.disabled = !between; control.second.hidden = !between;
  control.first.setAttribute("aria-label", control.name + " : " + (between ? "borne basse" : "valeur") + unit);
  control.second.setAttribute("aria-label", control.name + " : borne haute" + unit);
  control.first.placeholder = (between ? "Min · " : "") + (control.unit || control.placeholder || "");
  control.second.placeholder = "Max · " + (control.unit || control.placeholder || "");
 }
 function readFilterValue(field, control) {
  const value = field.value.trim();
  if (!value) return {missing: true};
  if (control.type === "number") {
   const number = value.replace(/\s/g, "").replace(",", ".");
   if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(number) || !Number.isFinite(Number(number)))
    return {error: "Nombre invalide."};
   return {value: Number(number)};
  }
  if (control.type === "date") {
   if (!field.validity.valid || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return {error: "Date invalide."};
   return {value};
  }
  return {value: normalise(value.replace(/\s+/g, " "))};
 }
 function compareValues(a, b, index) {
  return index < 2 ? a.localeCompare(b, "fr") : a - b;
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
    filterError(control, "Bornes inversées.", fields); invalid++; return;
   }
   conditions.push({index, operator: operator.value, lower: values[0].value, upper: values[1]?.value});
  });
  const messages = [conditions.length ?
   conditions.length + " condition" + (conditions.length > 1 ? "s actives." : " active.") : "Aucun filtre de colonne."];
  if (pending) messages.push(pending + " condition" + (pending > 1 ? "s à compléter" : " à compléter") + " (non appliquée" + (pending > 1 ? "s)." : ")."));
  if (invalid) messages.push(invalid + " condition" + (invalid > 1 ? "s invalides" : " invalide") + " (non appliquée" + (invalid > 1 ? "s)." : ")."));
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
 const distance = v => known(v) ? (v / 1000).toFixed(1).replace(".", ",") + " km" : "—";
 const duration = v => {
  if (!known(v)) return "—";
  const minutes = Math.round(v / 60), h = Math.floor(minutes / 60), m = minutes % 60;
  return h ? h + " h " + String(m).padStart(2, "0") : m + " min";
 };
 let column = 0, ascending = false, origin = data.origine, choices = [data.origine], controller = null;
 let lastRequest = -Infinity;
 let requestQueue = Promise.resolve();
 const routeCache = new Map(), cityCache = new Map();
 function readStorage(name, fallback) {
  try { return JSON.parse(localStorage.getItem(name)) || fallback; } catch { return fallback; }
 }
 function writeStorage(name, value) {
  try { localStorage.setItem(name, JSON.stringify(value)); } catch { /* cache mémoire si stockage interdit ou plein */ }
 }
 function fresh(route) {
  if (!route || typeof route !== "object") return false;
  const age = Date.now() - Date.parse(route.date_route);
  return age >= 0 && age < (route.erreur_route ? 86400000 : 30 * 86400000) &&
   (route.erreur_route ? route.route_cacheable === true : known(route.distance_route_m) && known(route.duree_route_s));
 }
 for (const entries of [readStorage("gpx2dash.routes.v1", {}), data.cache]) {
  for (const [k, route] of Object.entries(entries)) {
   if (fresh(route) && (!routeCache.has(k) ||
    Date.parse(route.date_route) > Date.parse(routeCache.get(k).date_route))) routeCache.set(k, route);
  }
 }
 function saveCache() {
  for (const [k, route] of routeCache) if (!fresh(route)) routeCache.delete(k);
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
  count.textContent = visible + " / " + rows.length + " trace(s)";
  empty.hidden = visible !== 0;
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
   return (ascending ? 1 : -1) * (column >= 2 ? Number(av) - Number(bv) : av.localeCompare(bv, "fr"));
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
  let completed = 0;
  data.traces.forEach(trace => {
   const row = rowById.get(trace.id);
   if (!row) return;
   const route = routes.get(key(trace.position, city.position)) || {};
   const tooltip = route.erreur_route || (route.date_route ?
    "OSRM, relevé le " + route.date_route + ". Sans trafic en temps réel." : "Trajet non renseigné.");
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
  document.getElementById("route-note").textContent =
   "Trajets aller en voiture calculés par OSRM, sans trafic en temps réel, jusqu’à la route accessible la plus proche du départ. " +
   "L’approche à pied n’est pas incluse. " + (data.nombre_valides - completed) +
   " trajet(s) non renseigné(s) ; la raison apparaît au survol des cellules.";
  sort(); refreshSearch();
  return completed;
 }
 function abortError() { return new DOMException("Calcul annulé.", "AbortError"); }
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
   if (response.status === 429) throw new Error("Service occupé (HTTP 429). Patientez quelques instants, puis relancez le calcul.");
   if (!response.ok && response.status !== 400) throw new Error("Service indisponible (HTTP " + response.status + ").");
   const result = await response.json();
   if (!response.ok && !result.code) throw new Error("Requête refusée.");
   return result;
  } catch (error) {
   if (signal && signal.aborted) throw abortError();
   if (error.name === "AbortError") throw new Error("Délai du service dépassé. Réessayez.");
   if (error instanceof TypeError) throw new Error("Connexion au service impossible. Vérifiez votre accès Internet.");
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
  status.textContent = "Recherche de la ville…";
  try {
   let cities = cityCache.get(normalise(query));
   if (!cities) {
    const json = await request(data.geocodeur + "?" + new URLSearchParams({
     q: query, limit: "8", lang: "fr", osm_tag: "place"
    }));
    if (!Array.isArray(json.features)) throw new Error("Réponse de recherche incomplète.");
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
    cityCache.set(normalise(query), cities);
   }
   setChoices(cities);
   status.textContent = cities.length ? "Sélectionnez la ville, puis cliquez sur « Calculer les trajets »." :
    "Aucune ville trouvée. Précisez le département ou le pays.";
  } catch (error) {
   setChoices([]);
   status.textContent = error.message;
  } finally { setBusy(false); }
 }
 form.addEventListener("submit", searchCities);
 input.addEventListener("input", () => {
  setChoices([]);
  status.textContent = "Cliquez sur « Rechercher » pour trouver la ville.";
 });
 async function matrix(destinations, city, signal, priorityOrigin = false) {
  const positions = [city.position, ...destinations];
  // FOSSGIS répartit les requêtes par continent majoritaire dans les coordonnées.
  if (priorityOrigin) positions.push(...destinations.map(() => city.position));
  const coordinates = positions.map(p => p[1].toFixed(6) + "," + p[0].toFixed(6)).join(";");
  const json = await request(data.serveur + "/table/v1/driving/" + coordinates + "?" +
   new URLSearchParams({sources: "0", destinations: destinations.map((_, i) => i + 1).join(";"),
    annotations: "distance,duration", generate_hints: "false"}), signal);
  if (json.code !== "Ok") throw Object.assign(new Error("OSRM : aucun point routier ou itinéraire trouvé."), {code: json.code});
  const distances = json.distances && json.distances[0], durations = json.durations && json.durations[0];
  const points = json.destinations, source = json.sources && json.sources[0];
  if (!Array.isArray(distances) || !Array.isArray(durations) || !Array.isArray(points) || !source ||
   [distances, durations, points].some(list => list.length !== destinations.length))
   throw new Error("OSRM : réponse incomplète.");
  if (source.distance > 1000 && !priorityOrigin)
   return matrix(destinations, city, signal, true);
  const timestamp = new Date().toISOString();
  return destinations.map((_, i) => {
   const route = {date_route: timestamp, route_cacheable: true};
   if (source.distance > 1000) route.erreur_route = "La ville de départ est à plus de 1 km du réseau routier.";
   else if (distances[i] == null || durations[i] == null) route.erreur_route = "Aucune liaison routière depuis la ville de départ.";
   else if (!known(distances[i]) || !known(durations[i])) throw new Error("OSRM : distance ou durée invalide.");
   else if (points[i].distance > 1000) route.erreur_route = "Aucune liaison routière trouvée à proximité du départ de la trace (rayon de 1 km).";
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
   if (fresh(routeCache.get(group.key))) { results.set(group.key, routeCache.get(group.key)); finished += group.count; }
   else missing.push(group);
  });
  const progress = () => { status.textContent = "Calcul depuis " + city.libelle + " : " + finished + " / " + data.traces.length + " traces traitées…"; };
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
   status.textContent = completed + " trajets renseignés depuis " + city.libelle + ". " +
    (data.nombre_valides - completed) + " non renseignés.";
  } catch (error) {
   status.textContent = (error.name === "AbortError" ? "Calcul annulé." : error.message) +
    " Les valeurs affichées correspondent à " + origin.libelle + ". Les lots terminés sont conservés pour reprendre.";
  } finally { controller = null; setBusy(false); }
 });
 cancelButton.addEventListener("click", () => { if (controller) controller.abort(); });
 setChoices([data.origine]);
 const saved = readStorage("gpx2dash.origin.v1", null);
 if (saved && typeof saved.libelle === "string" && validPosition(saved.position)) {
  const routes = new Map();
  data.traces.forEach(trace => {
   const k = key(trace.position, saved.position);
   if (fresh(routeCache.get(k))) routes.set(k, routeCache.get(k));
  });
  if (data.traces.every(trace => routes.has(key(trace.position, saved.position)))) {
   applyOrigin(saved, routes); setChoices([saved]); input.value = saved.libelle;
   status.textContent = "Dernier départ restauré : " + saved.libelle + ". Résultats repris du cache.";
  }
 }
 initialiserCarteTraces({data, table, getOrigin: () => origin, request, key, distance, duration, known});
 refreshSearch();
})();
