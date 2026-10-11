/* Carte de la trace et de son accès routier ; les segments GPX sont embarqués. */
function initialiserCarteTraces(options) {
 "use strict";
 const {t, text: message} = dashboardI18n;
 const {data, table, getOrigin, request, key, distance, duration, known} = options;
 const traces = new Map(data.traces.map(trace => [trace.id, trace]));
 const dialog = document.getElementById("map-dialog"), container = document.getElementById("trace-map");
 const status = document.getElementById("map-status"), overviewButton = document.getElementById("map-overview");
 const traceButton = document.getElementById("map-trace"), geometryCache = new Map();
 const catalogueButton = document.getElementById("map-catalogue");
 const onlyVisible = document.getElementById("map-only-visible");
 const rowById = new Map(Array.from(table.tBodies[0].rows, row => [row.dataset.id, row]));
 const mappedTraces = Array.from(traces.values()).filter(trace => trace.segments.length && rowById.has(trace.id));
 let map = null, traceLayer = null, roadLayer = null, catalogueLayer = null, markers = null, active = null, controller = null;
 let displayedIds = null;
 let bodyOverflow = "";
 const tilesNote = document.getElementById("map-tiles-note"), failedTiles = new Set();
 function noteTiles() { tilesNote.hidden = failedTiles.size === 0; }
 function textNode(text) {
  const element = document.createElement("span"); element.textContent = text; return element;
 }
 function fitTrace() {
  if (traceLayer) map.fitBounds(traceLayer.getBounds(), {padding: [28, 28], maxZoom: 16, animate: false});
 }
 function fitAll() {
  if (active?.mode === "catalogue") {
   const bounds = catalogueLayer && catalogueLayer.getBounds();
   if (bounds && bounds.isValid()) map.fitBounds(bounds, {padding: [28, 28], maxZoom: 16, animate: false});
   return;
  }
  if (!traceLayer || !active) return;
  const bounds = traceLayer.getBounds().extend(active.city.position);
  if (roadLayer) bounds.extend(roadLayer.getBounds());
  map.fitBounds(bounds, {padding: [28, 28], maxZoom: 16, animate: false});
 }
 function ensureMap() {
  if (map) return;
  map = L.map(container, {scrollWheelZoom: true, minZoom: 2, maxZoom: 19});
  map.createPane("road").style.zIndex = 410;
  map.createPane("gpx").style.zIndex = 420;
  L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
   maxNativeZoom: 17, maxZoom: 19, updateWhenIdle: true, keepBuffer: 1,
   attribution: 'Data: &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>, SRTM | Map: &copy; <a href="https://opentopomap.org" target="_blank" rel="noopener noreferrer">OpenTopoMap</a> (<a href="https://creativecommons.org/licenses/by-sa/3.0/" target="_blank" rel="noopener noreferrer">CC-BY-SA</a>)'
  }).on("tileerror", event => { failedTiles.add(event.tile); noteTiles(); })
   .on("tileload", event => { failedTiles.delete(event.tile); noteTiles(); })
   .on("tileunload", event => { failedTiles.delete(event.tile); noteTiles(); }).addTo(map);
  markers = L.layerGroup().addTo(map);
  L.control.scale({imperial: false}).addTo(map);
  new ResizeObserver(() => { if (dialog.open) map.invalidateSize({pan: false}); }).observe(container);
 }
 function showDialog() {
  if (!dialog.open) {
   bodyOverflow = document.body.style.overflow;
   dialog.showModal(); document.body.style.overflow = "hidden";
  }
  ensureMap();
  map.zoomControl.setPosition(active?.mode === "catalogue" ? "bottomright" : "topleft");
  map.invalidateSize({pan: false});
 }
 function clearLayers() {
  for (const layer of [traceLayer, roadLayer, catalogueLayer]) if (layer) layer.remove();
  traceLayer = roadLayer = catalogueLayer = null;
  displayedIds = null;
  markers.clearLayers();
 }
 function setMode(mode) {
  const catalogue = mode === "catalogue";
  container.dataset.mode = mode;
  traceButton.hidden = catalogue;
  document.getElementById("map-filter-control").hidden = !catalogue;
  document.querySelectorAll(".map-legend .road, .map-legend .gpx").forEach(el => el.hidden = catalogue);
  document.getElementById("map-catalogue-legend").hidden = !catalogue;
  document.getElementById("map-osm").hidden = catalogue;
  const kml = document.getElementById("map-kml");
  kml.hidden = !catalogue || !data.kml;
  if (data.kml) kml.href = data.kml;
  const label = catalogue ? "Carte interactive des traces du KML agrégé" : "Carte interactive du trajet routier et de la trace GPX";
  container.setAttribute("data-i18n-aria-label", label);
  container.setAttribute("aria-label", t(label));
 }
 function finishClose() {
  // A queued close event from the previous opening must not cancel a newly opened map.
  if (dialog.open) return;
  if (controller) controller.abort();
  controller = null; active = null;
  if (map) map.closePopup();
  document.body.style.overflow = bodyOverflow;
 }
 function close() { if (dialog.open) dialog.close(); finishClose(); }
 document.getElementById("map-close").addEventListener("click", close);
 dialog.addEventListener("close", finishClose);
 dialog.addEventListener("click", event => {
  if (event.target !== dialog) return;
  const bounds = dialog.getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right ||
   event.clientY < bounds.top || event.clientY > bounds.bottom) close();
 });
 traceButton.addEventListener("click", fitTrace);
 overviewButton.addEventListener("click", fitAll);
 function popupContent(trace) {
  const row = rowById.get(trace.id), popup = document.createElement("div");
  popup.className = "map-popup";
  const title = document.createElement("h3"); title.textContent = trace.id; popup.appendChild(title);
  const stats = document.createElement("dl");
  for (const [index, label] of [[0, "Date"], [1, "Lieu de départ"], [2, "Distance de la trace"],
   [3, "Dénivelé D+ / D−"], [4, "Durée de la trace"], [5, "Distance de route"],
   [6, "Durée de route"], [7, "Goudron longé (OSM)"]]) {
   const term = document.createElement("dt"), value = document.createElement("dd");
   term.textContent = t(label);
   const cell = row.cells[index];
   value.textContent = index === 0 ? cell.querySelector(".date").textContent :
    index === 1 ? cell.firstChild.textContent :
    Array.from(cell.childNodes, node => node.textContent.trim()).filter(Boolean).join(" · ");
   stats.append(term, value);
  }
  popup.appendChild(stats);
  const origin = document.createElement("p");
  origin.textContent = t("Trajet aller depuis {city}", {city: getOrigin().libelle}); popup.appendChild(origin);
  const actions = document.createElement("div"); actions.className = "map-popup-actions";
  const original = row.querySelector(".trace-name a[download]");
  if (original) {
   const download = original.cloneNode(false);
   download.textContent = t("Télécharger le GPX original"); actions.appendChild(download);
  }
  const link = row.querySelector(".route-link");
  if (link) {
   const button = document.createElement("button"); button.type = "button";
   button.textContent = t("Voir l’itinéraire et la trace");
   button.addEventListener("click", () => open(trace, row, link).catch(mapError));
   actions.appendChild(button);
  }
  popup.appendChild(actions);
  return popup;
 }
 function catalogueStatus(n) {
  message(status, n ? "{n} / {total} trace(s) affichée(s). Cliquez sur une trace pour voir ses informations." :
   "Aucune trace géolocalisée ne correspond aux filtres.", {n, total: mappedTraces.length});
 }
 function refreshCatalogue(fit = false) {
  if (active?.mode !== "catalogue") return;
  const selected = mappedTraces.filter(trace => !onlyVisible.checked || !rowById.get(trace.id).hidden);
  const ids = JSON.stringify(selected.map(trace => trace.id));
  catalogueStatus(selected.length);
  container.dataset.catalogueCount = String(selected.length);
  if (ids !== displayedIds) {
   if (catalogueLayer) catalogueLayer.remove();
   displayedIds = ids;
   catalogueLayer = L.geoJSON({type: "FeatureCollection", features: selected.map(trace => ({
    type: "Feature", properties: {id: trace.id, color: trace.color},
    geometry: {type: "MultiLineString", coordinates: trace.segments}
   }))}, {
    style: feature => ({color: feature.properties.color, weight: 3, opacity: .9, pane: "gpx", className: "catalogue-path"}),
    onEachFeature: (feature, layer) => {
     const trace = traces.get(feature.properties.id);
     layer.bindTooltip(() => textNode(trace.id));
     layer.bindPopup(() => popupContent(trace), {maxWidth: 330, minWidth: 230});
     layer.on("add", () => {
      const element = layer.getElement();
      element.dataset.traceId = trace.id;
      element.setAttribute("tabindex", "0");
      element.setAttribute("role", "button");
      element.setAttribute("aria-label", t("Détails de la trace : {name}", {name: trace.id}));
      element.addEventListener("keydown", event => {
       if (event.key === "Enter" || event.key === " ") { event.preventDefault(); layer.openPopup(); }
      });
     });
     layer.on("popupopen", () => layer.setStyle({weight: 5}));
     layer.on("popupclose", () => layer.setStyle({weight: 3}));
    }
   }).addTo(map);
  } else {
   catalogueLayer.eachLayer(layer => {
    layer.getElement().setAttribute("aria-label", t("Détails de la trace : {name}", {name: layer.feature.properties.id}));
    if (layer.isPopupOpen()) layer.getPopup().setContent(popupContent(traces.get(layer.feature.properties.id)));
   });
  }
  if (fit) fitAll();
 }
 function openCatalogue() {
  if (controller) controller.abort();
  controller = null;
  active = {mode: "catalogue"};
  const title = document.getElementById("map-title");
  title.dataset.i18n = "KML agrégé"; title.textContent = t("KML agrégé");
  message(document.getElementById("map-origin"), "Parcours regroupés dans le KML");
  document.getElementById("map-download").hidden = true;
  setMode("catalogue");
  showDialog(); clearLayers();
  delete container.dataset.traceId; delete container.dataset.origin;
  container.dataset.road = "none";
  noteTiles();
  refreshCatalogue(true);
 }
 function mapError(error) {
  message(status, "Carte indisponible : {error}", {error: error.message});
  container.dataset.road = "unavailable";
 }
 catalogueButton.disabled = mappedTraces.length === 0;
 catalogueButton.addEventListener("click", () => { try { openCatalogue(); } catch (error) { mapError(error); } });
 onlyVisible.addEventListener("change", () => refreshCatalogue(true));
 table.addEventListener("dashboard-filter", () => refreshCatalogue());
 document.addEventListener("dashboard-language", () => refreshCatalogue());
 async function geometry(trace, city, signal) {
  const cacheKey = key(trace.position, city.position);
  if (geometryCache.has(cacheKey)) return geometryCache.get(cacheKey);
  const coordinates = [city.position, trace.position].map(p => p[1].toFixed(6) + "," + p[0].toFixed(6)).join(";");
  const json = await request(data.serveur + "/route/v1/driving/" + coordinates + "?" + new URLSearchParams({
   geometries: "geojson", overview: "full", steps: "false", alternatives: "false", generate_hints: "false"
  }), signal);
  if (json.code !== "Ok") throw new Error(t("Aucun itinéraire routier trouvé depuis cette ville."));
  const route = json.routes && json.routes[0], points = json.waypoints;
  if (!route || !route.geometry || route.geometry.type !== "LineString" ||
   !Array.isArray(route.geometry.coordinates) || route.geometry.coordinates.length < 2 ||
   !route.geometry.coordinates.every(p => Array.isArray(p) && p.length >= 2 &&
    Number.isFinite(p[0]) && Number.isFinite(p[1]) && Math.abs(p[0]) <= 180 && Math.abs(p[1]) <= 90) ||
   !known(route.distance) || !known(route.duration) || !Array.isArray(points) || points.length !== 2 ||
   !points.every(p => known(p.distance))) throw new Error(t("Réponse routière incomplète."));
  if (points.some(point => point.distance > 1000))
   throw new Error(t("Aucune liaison routière trouvée à proximité des points de départ (rayon de 1 km)."));
  geometryCache.set(cacheKey, route);
  return route;
 }
 async function open(trace, row, link) {
  if (controller) controller.abort();
  controller = new AbortController();
  const signal = controller.signal, city = getOrigin();
  active = {mode: "trace", trace, city};
  setMode("trace");
  document.getElementById("map-title").removeAttribute("data-i18n");
  document.getElementById("map-title").textContent = trace.id;
  message(document.getElementById("map-origin"), "Trajet aller depuis {city}", {city: city.libelle});
  document.getElementById("map-osm").href = link.href;
  const original = row.querySelector(".trace-name a[download]"), download = document.getElementById("map-download");
  download.hidden = !original;
  if (original) download.href = original.href;
  message(status, "Trace GPX affichée. Chargement de l’itinéraire routier…");
  tilesNote.hidden = true;
  noteTiles();
  showDialog(); clearLayers();
  traceLayer = L.geoJSON({type: "MultiLineString", coordinates: trace.segments}, {
   style: {color: "#c54f36", weight: 4, opacity: 1, pane: "gpx", className: "gpx-path"}
  }).addTo(map);
  L.circleMarker(city.position, {radius: 6, weight: 3, color: "#2467ae", fillColor: "#fff", fillOpacity: 1, pane: "markerPane"})
   .bindTooltip(textNode(t("Départ routier : {city}", {city: city.libelle}))).addTo(markers);
  L.circleMarker(trace.position, {radius: 6, weight: 3, color: "#c54f36", fillColor: "#fff", fillOpacity: 1, pane: "markerPane"})
   .bindTooltip(textNode(t("Départ de la trace GPX"))).addTo(markers);
  map.invalidateSize({pan: false}); fitTrace();
  container.dataset.traceId = trace.id;
  container.dataset.origin = city.position.join(",");
  container.dataset.road = "loading";
  try {
   const route = await geometry(trace, city, signal);
   if (signal.aborted || !dialog.open) return;
   roadLayer = L.geoJSON(route.geometry, {
    style: {color: "#2467ae", weight: 5, opacity: .85, pane: "road", className: "road-path"}
   }).addTo(map);
   container.dataset.road = "ready";
   message(status, "Trajet routier : {distance} · {duration}. Trace GPX affichée en orange.", () => ({distance: distance(route.distance), duration: duration(route.duration)}));
   fitAll();
  } catch (error) {
   if (signal.aborted || !dialog.open) return;
   container.dataset.road = "unavailable";
   message(status, "{error} La trace GPX reste affichée.", {error: error.message});
   fitTrace();
  }
 }
 table.addEventListener("click", event => {
  const link = event.target.closest(".route-link");
  if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  const row = link.closest("tr"), trace = traces.get(row.dataset.id);
  if (!trace || !trace.segments.length) return;
  event.preventDefault();
  open(trace, row, link).catch(mapError);
 });
}
