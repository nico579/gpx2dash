"""Stable colours shared by the aggregated KML and dashboard map."""
import colorsys
import zlib


def couleur_html(nom):
    hue = (zlib.crc32(nom.encode("utf-8")) % 360) / 360.0
    channels = colorsys.hsv_to_rgb(hue, 0.85, 0.9)
    return "#" + "".join(f"{int(channel * 255):02x}" for channel in channels)


def couleur_kml(nom):
    colour = couleur_html(nom)
    return "ff" + colour[5:7] + colour[3:5] + colour[1:3]
