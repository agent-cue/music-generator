# Music Generator

Eigene Songs lokal auf dem Mac erzeugen – ohne Limits, ohne Abo, ohne Cloud.
Web-Oberfläche für [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5) über
[acestep.cpp](https://github.com/ServeurpersoCom/acestep.cpp) (Metal).

Ausführliche Anleitung mit Bildern: **[Installationsanleitung.pdf](Installationsanleitung.pdf)**

## Installation

Voraussetzungen: Mac mit Apple Silicon (M1–M4), mindestens 8 GB Arbeitsspeicher, 7–11 GB frei.

```bash
git clone <LINK-ZUM-PROJEKT> ~/MusicGenerator
open ~/MusicGenerator/Install.command
```

Der Installer

1. prüft Chip, Arbeitsspeicher und freien Platz,
2. schlägt das passende Sprachmodell vor (0.6B unter 12 GB, 1.7B bis 24 GB, 4B darüber),
3. installiert was fehlt: Apple-Entwicklerwerkzeuge, `uv`, `cmake` (ohne Homebrew, ohne Passwort),
4. baut acestep.cpp in der getesteten Version (`b7ba6d9`),
5. lädt nur die benötigten Modelle (fortsetzbar),
6. testet, ob das Sprachmodell auf dem Grafikchip richtig rechnet (sonst CPU, siehe unten),
7. richtet die Symbole für **Music Generator ON / OFF** ein und startet die App.

Er kann jederzeit erneut laufen; Erledigtes wird übersprungen.
Optionen: `--yes` (keine Rückfragen), `--lm 0.6B|1.7B|4B`, `--no-start`.

## Benutzen

- **Music Generator ON** startet Modellserver und App und öffnet http://localhost:8765
- **Music Generator OFF** beendet alles und schließt die Browser-Tabs

## Aktualisieren

```bash
cd ~/MusicGenerator && git pull
open Install.command
```

Songs und Einstellungen in `data/` bleiben erhalten.

## Aufbau

| Pfad | Inhalt |
|---|---|
| `Install.command` | Installer |
| `Music Generator ON/OFF.command` | Start und Stopp |
| `scripts/common.sh` | gemeinsame Pfade, Ports, acestep.cpp-Version |
| `scripts/metal_selftest.py` | Grafikchip-Test des Installers |
| `app/` | FastAPI-Backend: Queue, Bibliothek, Anbindung an ace-server |
| `static/` | Oberfläche |
| `engine/` | acestep.cpp und Modelle (vom Installer, nicht im Repo) |
| `data/` | Songs, Datenbank, Logs, `engine.conf` (nicht im Repo) |

## Grafikchip und die zwei Modi

Auf dem Apple M4 liefert das Sprachmodell unter Metal in acestep.cpp `b7ba6d9` fehlerhafte Ergebnisse
(0 Audio-Codes). Der Installer erkennt das mit einem kurzen Probelauf und schreibt nach `data/engine.conf`:

- `MODE=split` – Sprachmodell auf der CPU (Port 8086), Klangerzeugung auf Metal (Port 8085)
- `MODE=single` – alles auf einem Metal-Server (Port 8085)

Nach einem Update von acestep.cpp (`ACESTEP_REV` in `scripts/common.sh`) testet der Installer neu.

## Lizenz der Modelle

ACE-Step 1.5 steht unter Apache 2.0. Die Modelle werden beim Installieren von
[Hugging Face](https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF) geladen und sind nicht Teil dieses Repositorys.
Vor kommerzieller Nutzung die Lizenz- und Trainingsdaten-Lage selbst prüfen.
