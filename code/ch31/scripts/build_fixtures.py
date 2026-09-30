"""Erzeugt drei synthetische PDF-Fixtures; keine externen Dokumente."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures"
OUT.mkdir(exist_ok=True)
DATA = json.loads((ROOT / "data" / "cases.json").read_text(encoding="utf-8"))

digital = OUT / "digital.pdf"
pdf = canvas.Canvas(str(digital), pagesize=A4, invariant=1)
pdf.setTitle("Synthetisches Betriebshandbuch Kapitel 31")
pdf.setAuthor("Buchlabor, keine echte Richtlinie")
pdf.setFont("Helvetica", 16)
for index, line in enumerate(DATA["lines"]):
    pdf.drawString(68, 742 - index * 44, line)
pdf.save()

prefix = OUT / "scan_source"
subprocess.run(["pdftoppm", "-f", "1", "-l", "1", "-singlefile", "-r", "300",
                "-png", str(digital), str(prefix)], check=True)
image_path = prefix.with_suffix(".png")
with Image.open(image_path) as source:
    image = source.convert("RGB")
    pdf = canvas.Canvas(str(OUT / "scan_good.pdf"), pagesize=A4, invariant=1)
    pdf.drawImage(ImageReader(image), 0, 0, width=A4[0], height=A4[1])
    pdf.save()

    cropped = image.copy()
    draw = ImageDraw.Draw(cropped)
    # Die kritische vierte Zeile fehlt wie bei einem partiellen Scan.
    y = round((A4[1] - (742 - 3 * 44)) * 300 / 72)
    draw.rectangle((0, y - 100, cropped.width, y + 80), fill="white")
    pdf = canvas.Canvas(str(OUT / "scan_cropped.pdf"), pagesize=A4, invariant=1)
    pdf.drawImage(ImageReader(cropped), 0, 0, width=A4[0], height=A4[1])
    pdf.save()
image_path.unlink()
print("synthetic PDF fixtures: digital, scan_good, scan_cropped")
