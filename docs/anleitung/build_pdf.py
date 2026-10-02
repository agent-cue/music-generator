"""Erzeugt die Installationsanleitung für den Music Generator als PDF."""
import json
import sys
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

HERE = Path(__file__).parent
OUT = Path(sys.argv[1])

F = "/System/Library/Fonts/Supplemental/"
pdfmetrics.registerFont(TTFont("Arial", F + "Arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", F + "Arial Bold.ttf"))
pdfmetrics.registerFont(TTFont("Mono", F + "Courier New Bold.ttf"))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial", boldItalic="Arial-Bold")

# Farben aus der App
BG = HexColor("#0c0e12")
PANEL = HexColor("#1a1d24")
BORDER = HexColor("#2a2e38")
GOLD = HexColor("#d1a75c")
BRAND = HexColor("#b09f84")
LOGO_TXT = HexColor("#ddc8aa")
INK = HexColor("#1b1d22")
MUTED = HexColor("#6b7080")
LIGHT = HexColor("#f4f2ee")
LINE = HexColor("#e2ded6")
BLUE = HexColor("#6d8cff")
RED = HexColor("#d9534f")
GREEN = HexColor("#2f9e5b")

W, H = A4
M = 50  # Rand

body = ParagraphStyle("body", fontName="Arial", fontSize=10.5, leading=15.5, textColor=INK, alignment=TA_LEFT)
small = ParagraphStyle("small", parent=body, fontSize=9, leading=13, textColor=MUTED)
bold = ParagraphStyle("bold", parent=body, fontName="Arial-Bold")
cell = ParagraphStyle("cell", parent=body, fontSize=9.5, leading=13)
cellb = ParagraphStyle("cellb", parent=cell, fontName="Arial-Bold")


def para(c, text, x, y, w, style=body):
    """Zeichnet einen Absatz mit Oberkante y, gibt die neue y-Position zurück."""
    p = Paragraph(text, style)
    _, h = p.wrap(w, 1000)
    p.drawOn(c, x, y - h)
    return y - h


def logo(c, x, y, s):
    """Wellenform-Logo der App (Oberkante links = x, y; Kantenlänge s)."""
    k = s / 84
    c.setFillColor(HexColor("#3a3b3c"))
    c.setStrokeColor(BORDER)
    c.roundRect(x, y - s, s, s, 14 * k, stroke=1, fill=1)
    c.setFillColor(LOGO_TXT)
    for bx, by, bh in [(16, 36, 12), (25, 28, 28), (34, 20, 44), (43, 30, 24), (52, 24, 36), (61, 34, 16)]:
        c.roundRect(x + bx * k, y - (by + bh) * k, 5 * k, bh * k, 2.5 * k, stroke=0, fill=1)


def header(c, title, kicker):
    c.setFillColor(LIGHT)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(BG)
    c.rect(0, H - 92, W, 92, stroke=0, fill=1)
    logo(c, M, H - 24, 44)
    c.setFillColor(GOLD)
    c.setFont("Arial-Bold", 8.5)
    c.drawString(M + 58, H - 42, kicker.upper())
    c.setFillColor(white)
    c.setFont("Arial-Bold", 20)
    c.drawString(M + 58, H - 64, title)
    return H - 122


def footer(c, n):
    c.setFont("Arial", 8)
    c.setFillColor(MUTED)
    c.drawString(M, 28, "Music Generator · Installationsanleitung für macOS")
    c.drawRightString(W - M, 28, str(n))


def h2(c, text, y):
    c.setFillColor(INK)
    c.setFont("Arial-Bold", 13.5)
    c.drawString(M, y - 14, text)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.6)
    c.line(M, y - 21, M + 28, y - 21)
    return y - 34


def code(c, text, x, y, w):
    """Terminal-Befehl in dunkler Box, gibt neue y zurück."""
    lines = text.split("\n")
    h = 16 + 14 * len(lines)
    c.setFillColor(BG)
    c.roundRect(x, y - h, w, h, 6, stroke=0, fill=1)
    c.setFont("Mono", 9.5)
    for i, line in enumerate(lines):
        c.setFillColor(GOLD if "<" in line else LOGO_TXT)
        c.drawString(x + 12, y - 19 - 14 * i, line)
    return y - h


def note(c, text, y, color=GOLD, label="Hinweis"):
    """Hinweis-Kasten mit farbigem Balken links."""
    p = Paragraph(f"<b>{label}:</b> {text}", body)
    _, h = p.wrap(W - 2 * M - 26, 1000)
    c.setFillColor(white)
    c.setStrokeColor(LINE)
    c.roundRect(M, y - h - 18, W - 2 * M, h + 18, 6, stroke=1, fill=1)
    c.setFillColor(color)
    c.rect(M, y - h - 18, 4, h + 18, stroke=0, fill=1)
    p.drawOn(c, M + 16, y - h - 9)
    return y - h - 18


def badge(c, n, x, y, r=10, fill=GOLD, fg=BG):
    c.setFillColor(fill)
    c.setStrokeColor(BG)
    c.setLineWidth(1.2)
    c.circle(x, y, r, stroke=1, fill=1)
    c.setFillColor(fg)
    c.setFont("Arial-Bold", r * 1.05)
    c.drawCentredString(x, y - r * 0.37, str(n))


def arrow_down(c, x, y1, y2, color=MUTED):
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(1.4)
    c.line(x, y1, x, y2 + 5)
    p = c.beginPath()
    p.moveTo(x - 4, y2 + 6)
    p.lineTo(x + 4, y2 + 6)
    p.lineTo(x, y2)
    p.close()
    c.drawPath(p, stroke=0, fill=1)


def table(c, data, y, widths, head=True):
    rows = [[Paragraph(str(v), cellb if (head and r == 0) else cell) for v in row] for r, row in enumerate(data)]
    t = Table(rows, colWidths=widths)
    st = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.6, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 1), (-1, -1), white),
    ]
    if head:
        st += [("BACKGROUND", (0, 0), (-1, 0), HexColor("#ebe6dc")), ("LINEBELOW", (0, 0), (-1, 0), 1.2, GOLD)]
    t.setStyle(TableStyle(st))
    _, h = t.wrap(sum(widths), 1000)
    t.drawOn(c, M, y - h)
    return y - h


# ═════════════════════════════════════════════════════════════════ Seite 1: Titel
def page_cover(c):
    c.setFillColor(BG)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    # weicher Schimmer oben (blau links, gold rechts), wie in der App
    for i in range(40):
        a = 0.006
        c.setFillColor(BLUE, alpha=a)
        c.circle(40, H - 40, 380 - i * 9, stroke=0, fill=1)
        c.setFillColor(GOLD, alpha=a * 0.7)
        c.circle(W - 40, H - 40, 340 - i * 8, stroke=0, fill=1)
    c.setFillAlpha(1)

    y = H - 150
    # Logo + Abstand + Wortmarke füllen genau die Textbreite, beide gleich hoch
    ratio = 908 / 149
    wh = (W - 2 * M - 14) / (1 + ratio)
    logo(c, M, y, wh)
    c.drawImage(str(HERE / "alphatester.png"), M + wh + 14, y - wh, height=wh, width=wh * ratio, mask="auto")
    c.setFillColor(HexColor("#8a90a0"))
    c.setFont("Arial-Bold", 50)
    c.drawString(M, y - 170, "MUSIC")
    c.setFont("Arial-Bold", 30)
    c.drawString(M, y - 206, "GENERATOR")
    c.setStrokeColor(GOLD)
    c.setLineWidth(2)
    c.line(M, y - 228, M + 60, y - 228)
    c.setFillColor(white)
    c.setFont("Arial-Bold", 22)
    c.drawString(M, y - 266, "Installationsanleitung für macOS")
    c.setFillColor(HexColor("#b8bcc8"))
    c.setFont("Arial", 12)
    c.drawString(M, y - 290, "Eigene Songs lokal auf dem Mac erzeugen – ohne Limits, ohne Abo.")

    # Die drei Schritte als Vorschau
    sy = 250
    bw = (W - 2 * M - 24) / 3
    for i, (t, s) in enumerate([("Projekt holen", "per Git oder als Ordner"),
                                ("Install starten", "Doppelklick, der Rest läuft allein"),
                                ("Musik machen", "Music Generator ON")]):
        x = M + i * (bw + 12)
        c.setFillColor(PANEL)
        c.setStrokeColor(BORDER)
        c.roundRect(x, sy - 92, bw, 92, 10, stroke=1, fill=1)
        badge(c, i + 1, x + 24, sy - 26, 12)
        c.setFillColor(white)
        c.setFont("Arial-Bold", 12.5)
        c.drawString(x + 16, sy - 58, t)
        c.setFillColor(HexColor("#8a90a0"))
        c.setFont("Arial", 9)
        c.drawString(x + 16, sy - 75, s)

    c.setFillColor(HexColor("#6b7080"))
    c.setFont("Arial", 8.5)
    c.drawString(M, 52, "Basis: ACE-Step 1.5 (Apache 2.0) über acestep.cpp · läuft komplett lokal, kein Konto nötig")


# ═════════════════════════════════════════════════════════════════ Seite 2: Überblick
def page_overview(c):
    y = header(c, "Auf einen Blick", "Bevor es losgeht")
    y = para(c, "Der Music Generator erzeugt Songs direkt auf deinem Mac. Du beschreibst Stil und Stimmung, "
                "die App komponiert daraus Musik in Studioqualität (WAV, 48 kHz). Alles läuft lokal: "
                "keine Cloud, keine Download-Grenzen, dein Material bleibt auf deinem Rechner.", M, y, W - 2 * M)
    y -= 22
    y = h2(c, "Das brauchst du", y)
    rows = [["", "Voraussetzung", "Warum"],
            ["Mac", "Apple Silicon (M1, M2, M3, M4 …)", "Die Klangerzeugung nutzt den Grafikchip. Intel-Macs sind nicht getestet."],
            ["Speicher", "mindestens 8 GB Arbeitsspeicher, 16 GB empfohlen", "Bestimmt, welches Sprachmodell passt (siehe Seite 4)."],
            ["Festplatte", "7 bis 11 GB frei", "Modelle, Modellserver und Platz für deine Songs."],
            ["Internet", "für die Installation", "Die Modelle (4 bis 8 GB) werden einmalig geladen. Danach läuft alles offline."],
            ["Zeit", "etwa 15 bis 30 Minuten", "Hängt vor allem von der Download-Geschwindigkeit ab."]]
    y = table(c, rows, y, [70, 170, W - 2 * M - 240])
    y -= 26
    y = h2(c, "So läuft die Installation", y)

    # Drei große Schritte mit Pfeilen dazwischen
    bw = (W - 2 * M - 40) / 3
    bh = 128
    items = [("Projekt holen", "Den Projektordner per Git laden oder als Ordner bekommen."),
             ("Install starten", "Doppelklick auf „Install“. Der Installer prüft den Mac und richtet alles ein."),
             ("Musik machen", "„Music Generator ON“ öffnet die App im Browser.")]
    for i, (t, s) in enumerate(items):
        x = M + i * (bw + 20)
        c.setFillColor(white)
        c.setStrokeColor(LINE)
        c.roundRect(x, y - bh, bw, bh, 10, stroke=1, fill=1)
        badge(c, i + 1, x + 22, y - 24, 12)
        c.setFillColor(INK)
        c.setFont("Arial-Bold", 12)
        c.drawString(x + 14, y - 56, t)
        para(c, s, x + 14, y - 64, bw - 28, small)
        if i < 2:
            ax = x + bw + 4
            c.setFillColor(GOLD)
            p = c.beginPath()
            p.moveTo(ax, y - bh / 2 + 6)
            p.lineTo(ax + 12, y - bh / 2)
            p.lineTo(ax, y - bh / 2 - 6)
            p.close()
            c.drawPath(p, stroke=0, fill=1)
    y -= bh + 22
    note(c, "Der Installer fragt kaum etwas. Du kannst ihn jederzeit erneut starten, "
            "Erledigtes wird übersprungen und abgebrochene Downloads laufen weiter.", y, GOLD, "Gut zu wissen")
    footer(c, 2)


# ═════════════════════════════════════════════════════════════════ Seite 3: Schritt 1+2
def page_steps(c):
    y = header(c, "Schritt 1 und 2", "Projekt holen, Installer starten")
    y = h2(c, "1  Projekt holen", y)
    y = para(c, "Öffne das Programm <b>Terminal</b> (Spotlight: Cmd+Leertaste, „Terminal“ tippen) "
                "und füge diesen Befehl ein. Er lädt das Projekt in den Ordner <b>MusicGenerator</b> "
                "in deinem Benutzerordner:", M, y, W - 2 * M)
    y -= 10
    y = code(c, "git clone https://github.com/agent-cue/music-generator.git ~/MusicGenerator", M, y, W - 2 * M)
    y -= 8
    y = para(c, "Fehlen dem Mac die Apple-Entwicklerwerkzeuge, "
                "fragt macOS jetzt automatisch, ob sie installiert werden sollen: mit <b>Installieren</b> bestätigen, "
                "warten, dann den Befehl noch einmal ausführen.", M, y, W - 2 * M, small)
    y -= 12
    y = para(c, "<b>Ohne Git:</b> Hast du den Projektordner als ZIP oder per AirDrop bekommen, "
                "entpacke ihn an einen festen Ort, zum Beispiel in deinen Benutzerordner. "
                "Nicht im Download-Ordner lassen, dort wird gern aufgeräumt.", M, y, W - 2 * M)
    y -= 26

    y = h2(c, "2  Installer starten", y)
    y = para(c, "Öffne den Ordner im Finder und mach einen <b>Doppelklick auf „Install“</b>. "
                "Es öffnet sich ein Terminal-Fenster, in dem der Installer arbeitet. "
                "Alternativ im Terminal:", M, y, W - 2 * M)
    y -= 10
    y = code(c, "open ~/MusicGenerator/Install.command", M, y, W - 2 * M)
    y -= 16

    # Terminal-Mockup mit typischer Ausgabe
    lines = ["  MUSIC GENERATOR · Installation",
             "",
             "▸ Mac prüfen",
             "  Chip:        Apple M4 (arm64)",
             "  Arbeitsspeicher: 16 GB",
             "  Frei auf der Festplatte: 40 GB",
             "",
             "  Sprachmodell (größer = bessere Songs, mehr Speicher):",
             "    1) 0.6B  – 0,7 GB, für 8 GB Arbeitsspeicher",
             "    2) 1.7B  – 2,0 GB, für 16 GB",
             "    3) 4B    – 4,5 GB, ab 24 GB",
             "  Auswahl [Enter = 1.7B empfohlen] _"]
    th = 30 + 12.5 * len(lines)
    c.setFillColor(HexColor("#16181d"))
    c.setStrokeColor(BORDER)
    c.roundRect(M, y - th, W - 2 * M, th, 8, stroke=1, fill=1)
    for i, col in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
        c.setFillColor(HexColor(col))
        c.circle(M + 14 + i * 13, y - 11, 4, stroke=0, fill=1)
    c.setFont("Mono", 8.8)
    for i, line in enumerate(lines):
        c.setFillColor(GOLD if line.startswith("▸") or "Auswahl" in line else HexColor("#c9ccd4"))
        c.drawString(M + 14, y - 34 - 12.5 * i, line.replace("▸", ">"))
    y -= th + 14
    y = para(c, "Der Installer zeigt, was er auf deinem Mac gefunden hat, und schlägt das passende Sprachmodell vor. "
                "<b>Enter</b> übernimmt die Empfehlung, mit 1, 2 oder 3 wählst du selbst. "
                "Danach noch einmal Enter zum Starten, der Rest läuft von allein.", M, y, W - 2 * M)
    y -= 14
    note(c, "Bietet macOS nur „In den Papierkorb legen“ oder „Abbrechen“ an: <b>Abbrechen</b> wählen, dann "
            "<b>Systemeinstellungen › Datenschutz &amp; Sicherheit</b> öffnen und ganz unten bei „Install“ auf "
            "<b>Dennoch öffnen</b> klicken (Passwort oder Touch ID). Danach Install nochmal doppelklicken. "
            "Der Terminal-Weg steht auf Seite 4.", y, BLUE, "macOS-Warnung")
    footer(c, 3)


# ═════════════════════════════════════════════════════════════════ Seite 4: Was passiert
def page_flow(c):
    y = header(c, "Was der Installer macht", "Automatisch, Schritt für Schritt")
    steps = [
        ("Mac prüfen", "Chip, Arbeitsspeicher, macOS-Version und freien Platz ermitteln."),
        ("Modell wählen", "Passende Sprachmodell-Größe vorschlagen, Speicherplatz prüfen."),
        ("Werkzeuge", "Apple-Entwicklerwerkzeuge, uv (Python) und cmake, ohne Passwort und ohne Homebrew."),
        ("Modellserver bauen", "acestep.cpp in der getesteten Version herunterladen und für deinen Mac kompilieren."),
        ("Modelle laden", "Nur die Dateien, die dein Mac braucht, mit Fortschrittsbalken, fortsetzbar."),
        ("Grafikchip testen", "Probelauf: Rechnet das Sprachmodell auf dem Grafikchip richtig? Sonst nimmt es die CPU."),
        ("Symbole einrichten", "Grünes Start- und rotes Stopp-Symbol für „Music Generator ON/OFF“."),
        ("Loslegen", "Server starten und die App im Browser öffnen."),
    ]
    x0 = M
    bw = 300
    bh = 50
    gap = 13
    for i, (t, s) in enumerate(steps):
        top = y - i * (bh + gap)
        last = i == len(steps) - 1
        c.setFillColor(BG if last else white)
        c.setStrokeColor(GOLD if last else LINE)
        c.roundRect(x0, top - bh, bw, bh, 8, stroke=1, fill=1)
        badge(c, i + 1, x0 + 22, top - bh / 2, 11, GOLD, BG)
        c.setFillColor(white if last else INK)
        c.setFont("Arial-Bold", 11)
        c.drawString(x0 + 42, top - 19, t)
        para(c, s, x0 + 42, top - 25, bw - 54,
             ParagraphStyle("s", parent=small, fontSize=8.3, leading=10.5,
                            textColor=HexColor("#b8bcc8") if last else MUTED))
        if not last:
            arrow_down(c, x0 + 22, top - bh - 1, top - bh - gap + 1, GOLD)

    # Rechte Spalte: Modellwahl + Dauer
    rx = x0 + bw + 22
    rw = W - M - rx
    ry = y
    c.setFillColor(INK)
    c.setFont("Arial-Bold", 12)
    c.drawString(rx, ry - 12, "Welches Modell?")
    c.setStrokeColor(GOLD)
    c.line(rx, ry - 19, rx + 24, ry - 19)
    ry -= 30
    for ram, lm, dl, rec in [("8 GB", "0.6B", "4,4 GB", False), ("16 GB", "1.7B", "5,7 GB", True), ("24 GB", "4B", "8,1 GB", False)]:
        h = 58
        c.setFillColor(white)
        c.setStrokeColor(GOLD if rec else LINE)
        c.setLineWidth(1.4 if rec else 0.8)
        c.roundRect(rx, ry - h, rw, h, 8, stroke=1, fill=1)
        c.setFillColor(INK)
        c.setFont("Arial-Bold", 17)
        c.drawString(rx + 12, ry - 26, lm)
        c.setFont("Arial", 8.5)
        c.setFillColor(MUTED)
        c.drawString(rx + 12, ry - 42, f"ab {ram} Arbeitsspeicher")
        c.drawString(rx + 12, ry - 52, f"Download gesamt {dl}")
        if rec:
            c.setFillColor(GOLD)
            c.roundRect(rx + rw - 66, ry - 20, 56, 13, 6, stroke=0, fill=1)
            c.setFillColor(BG)
            c.setFont("Arial-Bold", 7)
            c.drawCentredString(rx + rw - 38, ry - 16, "HÄUFIGSTE")
        ry -= h + 8
    ry = para(c, "Größer heißt: Songaufbau, Tempo und Lyrics werden besser getroffen. "
                 "Das Klangmodell (SFT, hohe Qualität) ist bei allen gleich.",
              rx, ry - 2, rw, ParagraphStyle("r", parent=small, fontSize=8.5, leading=11.5))
    ry -= 20
    c.setFillColor(INK)
    c.setFont("Arial-Bold", 12)
    c.drawString(rx, ry - 12, "Wie lange?")
    c.setStrokeColor(GOLD)
    c.line(rx, ry - 19, rx + 24, ry - 19)
    ry -= 30
    for k, v in [("Modellserver bauen", "2 bis 5 Min."), ("Modelle laden", "je nach Leitung"),
                 ("Grafikchip-Test", "1 bis 2 Min."), ("Ein Song (1:30)", "etwa 2 bis 4 Min.")]:
        c.setFont("Arial", 8.8)
        c.setFillColor(INK)
        c.drawString(rx, ry - 10, k)
        c.setFillColor(MUTED)
        c.drawRightString(rx + rw, ry - 10, v)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        c.line(rx, ry - 15, rx + rw, ry - 15)
        ry -= 20
    # Unter beiden Spalten: wenn macOS die Datei blockiert
    yy = y - len(steps) * (bh + gap) + gap - 24
    yy = h2(c, "Wenn macOS die Datei blockiert", yy)
    yy = para(c, "Das passiert bei Dateien aus dem Internet, vor allem bei einem ZIP. Statt über die Systemeinstellungen "
                 "(Seite 3) geht es auch im Terminal in einem Schritt für den ganzen Ordner. Danach lassen sich Install "
                 "und Music Generator ON/OFF ohne Nachfrage öffnen:", M, yy, W - 2 * M)
    yy -= 8
    yy = code(c, "xattr -dr com.apple.quarantine ~/MusicGenerator", M, yy, W - 2 * M)
    yy -= 8
    para(c, "Mit <b>git clone</b> (Schritt 1) tritt die Warnung gar nicht erst auf.", M, yy, W - 2 * M, small)
    footer(c, 4)


# ═════════════════════════════════════════════════════════════════ Seite 5: Starten + App
def page_app(c):
    y = header(c, "Starten, beenden, loslegen", "Die App benutzen")
    # ON/OFF
    iw = 50
    for i, (img, t, s) in enumerate([("icon-on.png", "Music Generator ON", "startet alles und öffnet die App im Browser"),
                                     ("icon-off.png", "Music Generator OFF", "beendet alles und schließt die Browser-Tabs")]):
        x = M + i * ((W - 2 * M) / 2)
        c.drawImage(str(HERE / img), x, y - iw, iw, iw, mask="auto")
        c.setFillColor(INK)
        c.setFont("Arial-Bold", 11.5)
        c.drawString(x + iw + 12, y - 20, t)
        para(c, s, x + iw + 12, y - 26, (W - 2 * M) / 2 - iw - 20, small)
    y -= iw + 12
    y = para(c, "Beide liegen im Projektordner. Tipp: ins Dock ziehen. Die App läuft unter "
                "<b>http://localhost:8765</b>, die Fenster schließen sich nach dem Start selbst.", M, y, W - 2 * M, small)
    y -= 16
    y = h2(c, "Der Bildschirm", y)

    # Screenshot mit Markierungen (Positionen liefert capture.py in marks.json)
    mk = json.loads((HERE / "marks.json").read_text())["form"]
    iw_pt = 300
    ih_pt = iw_pt * mk["h"] / mk["w"]
    ix, iy = M, y - ih_pt
    c.setStrokeColor(BORDER)
    c.roundRect(ix - 1, iy - 1, iw_pt + 2, ih_pt + 2, 6, stroke=1, fill=0)
    c.drawImage(str(HERE / "form.png"), ix, iy, iw_pt, ih_pt)
    sc = iw_pt / mk["w"]
    for n, (px, py) in enumerate(mk["marks"], 1):
        badge(c, n, ix + px * sc, iy + ih_pt - py * sc, 7)

    legend = [
        ("Logo", "Geheimes Upload-Feld: Song darauf ziehen oder klicken. Die App analysiert ihn und füllt Prompt, Tempo und Länge aus."),
        ("Titel", "Nur zum Wiederfinden. Der Würfel schlägt einen Namen vor."),
        ("Prompt", "Deine Idee: Stimmung, Szene, Klang. Der Würfel würfelt eine Idee."),
        ("Stil", "Genre und Instrumente. Würfel: Vorschlag. Unter „Stile“ hängen Karten Begriffe an."),
        ("Länge", "10 Sekunden bis 5 Minuten, Standard 1:30."),
        ("BPM", "Tempo. Ganz links = Auto, das Modell wählt."),
        ("Lyrics", "Eingeklappt = instrumental. Würfel: „Automatisch“, das Modell schreibt beim Generieren eigene Texte. Aufgeklappt: Sprache und eigene Lyrics."),
        ("Erweitert", "Iterationen (Qualität), Varianz (Abwechslung), Tonart, Takt, Seed."),
        ("Generieren", "Unten die Zahl der Versionen (1 bis 10) wählen und los. Mehrere heißen dann A, B, C … Die Leiste bleibt beim Scrollen sichtbar."),
        ("Zahnrad", "Verbindungstest, Anordnung (untereinander oder nebeneinander) und „Nach Updates suchen“."),
    ]
    lx = ix + iw_pt + 18
    lw = W - M - lx
    ly = y
    st = ParagraphStyle("lg", parent=small, fontSize=8.4, leading=10.8, textColor=INK)
    for n, (t, s) in enumerate(legend, 1):
        badge(c, n, lx + 8, ly - 8, 7.5)
        ly = para(c, f"<b>{t}</b> · {s}", lx + 22, ly - 1, lw - 22, st) - 7.5
    footer(c, 5)


# ═════════════════════════════════════════════════════════════════ Seite 6: Bibliothek + Hilfe
def page_help(c):
    y = header(c, "Bibliothek, Updates, Hilfe", "Wenn der erste Song fertig ist")
    y = h2(c, "Ein Song in der Bibliothek", y)
    rk = json.loads((HERE / "marks.json").read_text())["row"]
    iw_pt = W - 2 * M
    ih_pt = iw_pt * rk["h"] / rk["w"]
    ix, iy = M, y - ih_pt - 10
    c.setFillColor(PANEL)
    c.roundRect(ix - 4, iy - 4, iw_pt + 8, ih_pt + 8, 6, stroke=0, fill=1)
    c.drawImage(str(HERE / "row.png"), ix, iy, iw_pt, ih_pt)
    sc = iw_pt / rk["w"]
    # Play steht links, die fünf Knöpfe rechts; Nummern über die Zeile
    for n, px in enumerate(rk["xs"], 1):
        badge(c, n, ix + px * sc, iy + ih_pt + 8, 7.5)
    y = iy - 16
    items = [("Play", "abspielen, mit Wellenform unten"), ("Stern", "als Favorit markieren"),
             ("WAV", "herunterladen, 48 kHz, 16 Bit"), ("Plus", "weitere Version mit neuem Seed"),
             ("Pfeil", "Einstellungen ins Formular übernehmen"), ("Kreuz", "löschen")]
    colw = (W - 2 * M) / 3
    st = ParagraphStyle("it", parent=small, fontSize=8.6, leading=11, textColor=INK)
    for i, (t, s) in enumerate(items):
        cx = M + (i % 3) * colw
        cy = y - (i // 3) * 26
        badge(c, i + 1, cx + 8, cy - 7, 7.5)
        para(c, f"<b>{t}</b> · {s}", cx + 22, cy, colw - 28, st)
    y -= 60
    y = para(c, "Titel lassen sich per Klick umbenennen. Die Zeile darunter zeigt "
                "<b>BPM · IT</b> (Iterationen) <b>· VAR</b> (Varianz) · Tonart · Länge. "
                "„Erstellt in …“ verschwindet, sobald du den Song zum ersten Mal abspielst.", M, y, W - 2 * M, small)
    y -= 20

    y = h2(c, "Aktualisieren", y)
    y = para(c, "Neue Version holen und den Installer noch einmal laufen lassen. Deine Songs bleiben erhalten.",
             M, y, W - 2 * M)
    y -= 8
    y = code(c, "cd ~/MusicGenerator && git pull\nopen Install.command", M, y, W - 2 * M)
    y -= 20

    y = h2(c, "Wenn etwas hakt", y)
    rows = [["Problem", "Lösung"],
            ["„Zu wenig Speicherplatz“", "Platz schaffen (Papierkorb leeren!), dann Install erneut starten. Die Meldung nennt, wie viel nötig ist."],
            ["Download abgebrochen", "Install erneut starten, der Download läuft an der Stelle weiter."],
            ["„OFFLINE“ oben in der App", "Music Generator OFF, dann ON. Hilft das nicht: Details im Ordner data/ (Logdateien)."],
            ["Song bricht mit Fehler ab", "Mauszeiger auf den Fehler halten zeigt den Grund. Mit dem Kreispfeil daneben neu versuchen."],
            ["Sehr langsam", "Erweitert: Iterationen senken (z. B. 30) oder kürzere Länge wählen."]]
    y = table(c, rows, y, [140, W - 2 * M - 140])
    y -= 20
    y = h2(c, "Deinstallieren", y)
    para(c, "Music Generator OFF, dann den Ordner <b>MusicGenerator</b> in den Papierkorb legen. "
            "Vorher den Unterordner <b>data/songs</b> sichern, falls du deine Songs behalten willst. "
            "Optional: das Hilfsprogramm uv liegt unter ~/.local/bin.", M, y, W - 2 * M)
    footer(c, 6)


c = canvas.Canvas(str(OUT), pagesize=A4)
c.setTitle("Music Generator – Installationsanleitung")
c.setAuthor("Alphatester")
for fn in (page_cover, page_overview, page_steps, page_flow, page_app, page_help):
    fn(c)
    c.showPage()
c.save()
print("ok", OUT)
