# GPX2DASH

[![EN · English](https://img.shields.io/badge/EN-English-958bea?style=for-the-badge)](README.md)
[![FR · Français](https://img.shields.io/badge/FR-Fran%C3%A7ais-34334b?style=for-the-badge)](README.fr.md)
[![CI](https://github.com/nico579/gpx2dash/actions/workflows/ci.yml/badge.svg)](https://github.com/nico579/gpx2dash/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/nico579/gpx2dash)](https://github.com/nico579/gpx2dash/releases/latest)

**GPX2DASH turns a folder of GPX tracks into a single KML file containing
the routes with recalculated elevation gain/loss, and an HTML dashboard
for comparing outings and planning how to reach them.**

## The two generated files

### A KML containing all tracks

All usable GPX files in the folder are collected into **one KML file**,
viewable in the dashboard or a compatible mapping application. Each GPX file retains
its own track and colour; gaps between recording segments stay separate.

Each track name includes its date or filename, starting place, distance,
**recalculated ascent** and duration. KML extended data stores the exact
**ascent/descent**, the elevation model, the calculation protocol and reasons
for any fallback to another source. Statistics are calculated before drawing
simplification, which defaults to 10 m with `--tolerance`.

### An HTML dashboard of the tracks

The dashboard contains **one row per GPX file** and eight columns:

| Column | Content |
|---|---|
| Date | Outing date |
| Track starting place | Nearest town to the first GPX point |
| Track distance | Route length in kilometres |
| Elevation gain/loss | Recalculated ascent and descent in metres |
| Track duration | Estimated moving time, or elapsed time when necessary |
| Driving distance | Driving distance from the chosen origin to the GPX start |
| Driving time | Estimated duration of the same drive, without live traffic |
| Distance alongside asphalt (OSM) | Track kilometres alongside a road with an explicitly mapped bituminous surface |

Columns support **sorting** and **combined filters**: `=`, `>`, `<` or
`Between`. A track must satisfy every active condition. For example:
10–20 km long, less than 600 m ascent, and less than 45 minutes away by car.
Column titles and filters remain visible while scrolling.

Choose the driving origin by **town or coordinates** when generating the
files; the town can then be changed in the dashboard. Clicking a row's route
link displays **the driving route and GPX track on the same map**.
Free-text search and original GPX downloads are also available.

Asphalt measurement uses the original GPX points and OpenStreetMap roads
retrieved through **Overpass**. By default, a portion must be within **15 m**
of the road axis and have a direction difference of at most **30°**.
Confirmed and uncertain surfaces are distinguished; this column supports
the same filters as the others.

Open the HTML by **double-clicking**: no web server is required. Reading,
sorting and filtering work offline. Driving routes use **OSRM** and town search
uses **Photon**, with no API key or billing account. Internet is used to fetch
missing data and display the map background.

## How elevation gain/loss is recalculated

The **gpx2elev** calculation engine, included in the project, applies the same
method to every track to calculate cumulative ascent **D+** and descent **D−**:

1. **Prepare the original route.** GPX coordinates are preserved without
   automatic position correction. Each segment is processed separately and
   resampled every **5 m** of horizontal distance, retaining its final point.
2. **Obtain a complete elevation profile.** The engine selects the first
   available model covering **every sampled position of the track**, in this
   order: **IGN LiDAR HD → Mapterhorn → FABDEM 1.2 → Copernicus GLO-30 →
   SRTM90**. A single model covers the entire track; an incomplete profile
   causes the next model to be tried.
3. **Smooth the profile.** A Gaussian filter with a standard deviation of
   **20 m of distance travelled** reduces small elevation fluctuations.
   The profile is extended at segment ends to limit edge effects.
4. **Identify climbs and descents.** A **2 m hysteresis** validates changes
   of direction: a climb/descent reversal, or the reverse, is accepted only
   after a change of at least 2 m from the extreme reached. Each segment's
   endpoints remain included.
5. **Sum the retained changes.** Increases give ascent; decreases give
   descent. Segment totals are added without introducing an elevation change
   across recording gaps.

If no model provides a complete profile, the engine applies the same
resampling, smoothing and threshold to **GPX elevations**, when complete.
The result is identified as a **filtered GPX fallback**. If no usable
elevation data is available, gain/loss remains **unknown**.

The dashboard and KML share these results, displayed to the nearest metre.
Exact values and comparisons with raw and filtered GPX elevations are stored
in the cache and KML extended data. Source GPX files are only read.
The complete protocol is documented in
[AGREG_DENIVELE.md](AGREG_DENIVELE.md) (in French).

Without `--from-cache`, the engine recalculates statistics and retrieves missing
elevation data. With `--from-cache`, it reuses valid statistics or cached
elevation profiles, then filtered GPX elevations; **no elevation data is
downloaded**.

## Install and run

Choose **one installation method**. The standalone bundle is recommended
for normal use. Running the Python source is an alternative if you want to
work with the code. **You do not need to run both commands.**

### Option 1: standalone bundle (recommended)

Download from [GitHub Releases](https://github.com/nico579/gpx2dash/releases):

| Platform | Archive |
|---|---|
| Windows x86_64 | `gpx2dash-windows-x86_64.zip` |
| Linux x86_64 | `gpx2dash-linux-x86_64.tar.gz` |
| macOS Apple Silicon | `gpx2dash-macos-arm64.tar.gz` |

Extract and keep the **entire `gpx2dash` folder**, including `_internal`.
Open a terminal in that folder and run a first generation with
elevation recalculation, routing and asphalt measurement:

~~~powershell
.\gpx2dash.exe "C:\path\to\gpx" --asphalt --html dashboard.html --kml tracks.kml --language en
~~~

Replace `C:\path\to\gpx` with the actual path to your GPX folder, then
double-click **dashboard.html** after the command finishes. On Linux/macOS
use `./gpx2dash`. The bundles include Python and dependencies, so no Python
installation is required. You can now skip the source installation section
and continue with [usage examples](#usage-examples).

They are **built and tested on native GitHub runners**, using locked
dependencies. Release assets include SHA-256 checksums and `SHA256SUMS.txt`.

The command fetches missing data and caches it. Add `--from-cache`
to regenerate without downloading elevation data.

### Option 2: run from source

Choose this method **instead of the bundle** to run or modify the Python
code. Python **3.12** and Git are required. The elevation engine is included:
no sibling project, Conda or Qt installation is needed.

Windows / PowerShell:

~~~powershell
git clone https://github.com/nico579/gpx2dash.git
cd gpx2dash
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 gpx2dash.py "C:\path\to\gpx" --asphalt --html dashboard.html --kml tracks.kml --language en
~~~

Linux/macOS:

~~~bash
git clone https://github.com/nico579/gpx2dash.git
cd gpx2dash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.txt
.venv/bin/python gpx2dash.py "/path/to/gpx" --asphalt --html dashboard.html --kml tracks.kml --language en
~~~

Replace the example path with your GPX folder. This source command produces
the same dashboard and KML as the bundle command. With no positional
argument, the program uses the sibling `gpx` folder if present, otherwise
the current directory.
Both `.gpx` and `.GPX` are accepted. Default output names are timestamped.

With the sources, try a **fully offline demonstration** using the synthetic example:

~~~powershell
.\.venv\Scripts\python.exe -X utf8 gpx2dash.py examples --from-cache --no-routing --html demonstration.html --kml demonstration.kml
~~~

Double-click **demonstration.html**. Routing and asphalt remain unknown until
data is downloaded. Personal GPX files, caches, screenshots and generated
HTML/KML files are excluded by `.gitignore`.

## Usage examples

The examples below use the **Windows bundle in PowerShell**. For a different
installation, replace only the command prefix:

| Installation | Command prefix |
|---|---|
| Windows bundle | `.\gpx2dash.exe` |
| Windows sources | `.\.venv\Scripts\python.exe -X utf8 gpx2dash.py` |
| Linux/macOS bundle | `./gpx2dash` |
| Linux/macOS sources | `.venv/bin/python gpx2dash.py` |

Keep the same parameters and replace `C:\path\to\gpx` with your GPX folder
(use a path appropriate to your system). Each example is a separate operation,
not a sequence of required steps.

## English / French and fixed headers

Select **EN · English / FR · Français** at the top of the dashboard.
The initial language follows the browser (French for a French browser,
English otherwise), or `--language en` / `--language fr`. The last language
chosen is saved in browser storage and takes precedence on subsequent opens.
Switching languages preserves active filters and sorting.

**Column titles and filters stay visible** while scrolling vertically inside
the table. Horizontal scrolling keeps headers aligned, including on mobile.
Printing includes the full table.

CLI parameters and `--help` are in English. Previous French parameters,
including `--depuis-cache`, remain accepted as hidden compatibility aliases.

## What does --from-cache change?

With **`--from-cache`**, verified statistics are reused when the GPX SHA-256
fingerprint and elevation protocol match. Date and duration are still read
from the original GPX. If statistics are absent, the engine uses local profiles,
then filtered GPX elevations. **No elevation data is downloaded.**

Without **`--from-cache`**, statistics are recalculated. The engine first uses
available terrain data and downloads missing data as needed, ranking full-track
coverage as IGN LiDAR HD, Mapterhorn, FABDEM, Copernicus GLO-30, then SRTM90.
If none covers the track, filtered GPX elevations are used. The first run can
download substantial terrain data. Original GPX files are read without modification.

These switches are independent:

| Parameter | Effect |
|---|---|
| `--from-cache` | Reuse verified statistics / local elevation data; no elevation downloads |
| `--no-routing` | Use routing cache only; no OSRM requests during generation |
| `--asphalt` | Download missing nearby OSM road surfaces with Overpass |
| no `--asphalt` | Reuse local asphalt measurements or road snapshots only |

To regenerate entirely from local data:

~~~powershell
.\gpx2dash.exe "C:\path\to\gpx" --from-cache --no-routing --html dashboard.html --kml tracks.kml
~~~

Source caches default to `.cache_gpx` in the project folder. Bundles use
`.cache_gpx` in the current directory. Set `--cache PATH` to choose another folder.

## Choose the driving origin

In the HTML:

1. Enter a town, e.g. **Toulon, France**, then click **Search**.
2. Select a match under **Selected town**.
3. Click **Calculate routes**.

The driving columns, OpenStreetMap links and overview update. Active filters
and sorting remain applied. The last origin and recent routes are saved in the
browser. On cancellation or service failure, displayed values retain their
previous origin; completed batches remain cached for resuming.

The default origin is Garéoult town hall, France (43.3293, 6.0458).
Set another initial town when generating:

~~~powershell
.\gpx2dash.exe "C:\path\to\gpx" --from-cache --origin-city "Toulon, Var, France" --html dashboard.html
~~~

Or use exact coordinates:

~~~powershell
.\gpx2dash.exe "C:\path\to\gpx" --from-cache --origin 43.1242 5.9280 --origin-name "My Toulon start"
~~~

The command line uses the first Photon result and prints its label.
The dashboard lets you choose among results. Searching a new town, calculating
uncached routes and loading map tiles require Internet. Reading the table,
searching, sorting and filtering work offline.

## Combine column filters

Each column has **=**, **>**, **<**, and **Between**, with inclusive bounds.
**All** disables that column's condition. Every active condition is combined
with **AND**, together with free-text search.

Distances use **km**, elevation gain uses **metres**, and durations use
**minutes** (90 means 1 h 30). Filters compare rounded displayed values;
sorting retains original precision. Decimal commas and points are accepted.
Dates use a calendar. Place comparisons ignore accents and case and use
alphabetical order; equality matches the complete town name.

Example: **track distance between 10 and 20 km**, **elevation gain < 600 m**,
**driving time < 45 minutes**. Unknown values are excluded when their column
has an active condition. Incomplete, invalid or reversed bounds are ignored
and reported beside the filter. **Clear filters** also clears free-text search.

## Distance alongside asphalt

Use **`--asphalt`** for the first download:

~~~powershell
.\gpx2dash.exe "C:\path\to\gpx" --from-cache --no-routing --asphalt --html dashboard.html
~~~

Measurement uses the **original GPX**, before simplification. A portion counts
within **15 metres** of an OSM road axis with a direction difference of
**30 degrees** or less, in either direction. Perpendicular crossings are
excluded. Sampling is at most 5 m, with headings evaluated over a 20 m window.
Disconnected segments are kept separate. Repeated passes count the distance
actually travelled; multiple nearby roads do not double-count distance.

Only explicit OSM **asphalt, chipseal, tarmac, bitumen, tar** surfaces are
confirmed. Missing or ambiguous surfaces, including **paved**, stay uncertain:
road type alone does not establish its surface. **≥** denotes a confirmed
minimum, followed by uncertain kilometres. With only uncertain surfaces the
cell shows a dash and the uncertain distance. Filters apply to the confirmed
minimum; unknown values are never treated as zero.

Download failures also leave a dash, with details in the tooltip.
**Rerun with `--asphalt` to resume missing tracks**. Successful measurements
are retained. Transient Overpass failures use bounded retries and respect
the server's requested delay.

Change tolerances with:

~~~powershell
.\gpx2dash.exe "C:\path\to\gpx" --from-cache --no-routing --asphalt --asphalt-tolerance 20 --asphalt-angle 30 --html dashboard.html
~~~

Distance tolerance accepts 1–50 m; angle accepts 1–60°. Measurements and road
snapshots are cached for **30 days** in `.cache_gpx/goudron_osm_v1.json` and
`.cache_gpx/goudron_osm/`, distinguished by fingerprint, tolerances, server
and protocol. Nearby tracks share batches, with at least three seconds between
Overpass requests. Choose an endpoint with `--overpass-server URL`.

These are estimates: missing OSM tags, GPS noise, parallel roads or bridges can
affect interpretation. See [OSM surfaces](https://wiki.openstreetmap.org/wiki/Key:surface).

## View the aggregated KML in the dashboard

Click **Aggregated KML map**, next to the catalogue search field.
The map displays every track with **the same colours as the KML**;
disconnected recording segments stay separate.

Select **Filtered tracks only** to show routes matching the table's search and
filters. **Overview** fits the displayed tracks. Clicking a track opens its
details: date, starting place, distance, gain/loss, duration, driving access
and asphalt alongside. Download the original GPX from the popup, or open
**the driving route and track**.

**Download complete KML** retrieves the generated file with all its tracks,
even when the map is filtered. Keep the KML at its generated location for this
link. Geometry is embedded in the HTML, so the global map works by opening
the file directly, without a local server. Map tiles require Internet;
tracks remain visible if tiles fail to load. Opening the global map does not
calculate any driving routes.

## Display the driving route and GPX track

Click **Driving route and GPX track** in a row. The dialog shows the one-way
drive from the current origin in **blue**, and the GPX track in **orange**.
**Overview** frames both; **Zoom to track** focuses on the outing.
Download the original GPX or open directions in OpenStreetMap from the dialog.

Simplified GPX geometry is embedded in the HTML, keeping recording gaps
separate. The original is preserved; displaying the track needs no upload.
OpenTopoMap tiles and OSRM geometry are fetched only when opening the map.
If either service fails, the GPX remains visible. Previously displayed driving
routes are cached during the browser session, per origin and destination.

[Leaflet 1.9.4](https://leafletjs.com/download.html), its CSS and BSD licence
are inlined. The map uses OpenTopoMap with visible OSM/SRTM attribution and
CC-BY-SA licence. Standard `tile.openstreetmap.org` was replaced because direct
`file://` pages do not provide its required HTTP referrer. Normal browser tile
caching is retained.

## Routing and service caches

OSRM returns one-way **driving** routes without live traffic, to the nearest
accessible road at the track's first point. Distance follows OSRM's fastest
route. Final walking access is excluded. Snapping farther than 1 km, or no road
connection, leaves unknown values with a tooltip.

Identical starts are grouped. Matrices use at most 25 destinations, with at
least 1.05 seconds between requests. Cache keys include server, origin and
destination. Routes are valid for 30 days; genuine route absences for 24 hours.
Network outages are not cached as absent routes. For mixed continents, a
second request fixes the origin region when the initial snap is too distant.

Python stores routes in `.cache_gpx/trajets_osrm_v1.json`. The HTML embeds
initial results and uses browser storage for subsequent calculations.
Public [OSRM routing](https://routing.openstreetmap.de/about.html),
[Photon](https://github.com/komoot/photon) and OpenTopoMap have limited capacity.
For heavier use, configure your own
[OSRM server](https://github.com/Project-OSRM/osrm-backend):

~~~powershell
.\gpx2dash.exe "C:\path\to\gpx" --osrm-server "http://localhost:5000"
~~~

It must expose the driving profile, distance/duration matrices and browser CORS.
Town search is triggered explicitly, not on every keystroke. Map tiles are
requested as needed, without bulk downloads.

## Statistics and implementation

Dates come from the first timestamped point in local time, then GPX metadata,
then the filename (`YYYY-MM-DD`, `YYYY_MM_DD` or `YYYYMMDD`).
Distance, elevation gain and duration are calculated before simplification.
Duration estimates moving time, falling back to elapsed time.
The starting place is the nearest town from the offline `reverse_geocoder`
database; the directions link uses GPX coordinates.
Unreadable files retain a row; unknown values are dashes.

The elevation protocol is in [AGREG_DENIVELE.md](AGREG_DENIVELE.md).
Required headless `gpx2elev` modules, version and provenance are included in
[gpx2elev/ORIGINE.md](gpx2elev/ORIGINE.md).
Geometry uses NumPy, native PyProj transforms and Shapely's spatial index.
Roads are prepared once per batch and selection is vectorized.
Conda is unnecessary; Numba JIT is not currently used.

## Development: tests, CI and releases

These commands are for contributors using the **source installation**,
from the cloned project folder. They are not needed to use a bundle.

`requirements.in` pins direct dependencies. `requirements.txt`,
`requirements-build.txt` and `requirements-dev.txt` lock transitive dependencies
and hashes. Install with `--require-hashes`.

~~~powershell
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.txt
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -v
.\.venv\Scripts\python.exe -X utf8 tools/smoke_bundle.py
.\.venv\Scripts\python.exe -X utf8 .qa/verifier_filtres.py --fixtures-only
.\.venv\Scripts\python.exe -X utf8 .qa/verifier_carte.py
.\.venv\Scripts\python.exe -X utf8 .qa/verifier_kml.py
.\.venv\Scripts\python.exe -X utf8 .qa/verifier_langues.py
~~~

Local browser checks use Microsoft Edge. Set `GPX2DASH_BROWSER=chromium` and
run `.\.venv\Scripts\python.exe -m playwright install chromium` to use Chromium, as CI does.
Developer previews use a loopback server for tests; users open HTML directly.

[CI](.github/workflows/ci.yml) runs Python tests on **Windows, Linux and macOS**.
Chromium tests cover EN/FR, all column operators, combined conditions, sorting,
origin changes, map/download/error behavior, aggregated KML colours, filters,
popups and downloads from local files, and fixed headers with vertical
and horizontal scrolling on desktop and mobile. GitHub runners then build
bundles and execute each against synthetic GPX and OSM fixtures, checking
KML/HTML, process workers, native geometry and geocoder data.

Tags `vX.Y.Z` trigger [release.yml](.github/workflows/release.yml), reusing the
same tests and builds. A tag must match `version.py`. Archives and checksums
are published only after **all** tests and executable smoke checks pass.
No locally built binaries are uploaded. The recipe is `build.py` and `gpx2dash.spec`.
