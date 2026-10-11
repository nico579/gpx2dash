/* Carte de la trace et de son accès routier ; les segments GPX sont embarqués. */
function initialiserCarteTraces(options) {
 "use strict";
 const {t, text: message} = dashboardI18n;
 const {data, table, getOrigin, request, key, distance, duration, known} = options;
 const traces = new Map(data.traces.map(trace => [trace.id, trace]));
 const dialog = document.getElementById("map-dialog"), container = document.getElementById("trace-map");
 const status = document.getElementById("map-status"), overviewButton = document.getElementById("map-overview");
 const traceButton = document.getElementById("map-trace"), geometryCache = new Map();
 let map = null, traceLayer = null, roadLayer = null, markers = null, active = null, controller = null;
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
 function finishClose() {
  // A queued close event from the previous opening must not cancel a newly opened map.
  if (dialog.open) return;
  if (controller) controller.abort();
  controller = null; active = null;
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
  active = {trace, city};
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
  if (!dialog.open) {
   bodyOverflow = document.body.style.overflow;
   dialog.showModal(); document.body.style.overflow = "hidden";
  }
  ensureMap();
  if (traceLayer) traceLayer.remove();
  if (roadLayer) { roadLayer.remove(); roadLayer = null; }
  markers.clearLayers();
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
  open(trace, row, link).catch(error => {
   message(status, "Carte indisponible : {error}", {error: error.message});
   container.dataset.road = "unavailable";
  });
 });
}
