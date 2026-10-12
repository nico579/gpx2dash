# Standalone CLI folder, with all resources used by the file:// HTML renderer.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH)
datas = [(str(root / name), ".") for name in (
    "tableau_bord_template.html", "tableau_bord.js", "carte_trace.js", "dashboard_i18n.js",
    "README.md", "README.fr.md", "AGREG_DENIVELE.md",
)]
datas += [(str(root / "assets/leaflet-1.9.4"), "assets/leaflet-1.9.4")]
# Le moteur installé lit assets/version.txt à l'import ; le reste de ses données sert à son interface.
datas += collect_data_files("gpx2elev", includes=["assets/version.txt"])
datas += collect_data_files("reverse_geocoder") + collect_data_files("rasterio") + collect_data_files("pyproj")
analysis = Analysis(
    [str(root / "gpx2dash.py")], pathex=[str(root)], binaries=[], datas=datas,
    hiddenimports=collect_submodules("rasterio"),
    hookspath=[], runtime_hooks=[], excludes=["tkinter", "PyInstaller"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="gpx2dash",
          debug=False, strip=False, upx=False, console=True)
COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name="gpx2dash")
