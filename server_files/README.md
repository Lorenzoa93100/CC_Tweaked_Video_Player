# VBC Server v2 — Video Block Converter for ComputerCraft: Tweaked

Réécriture du serveur [vbc-computercraft](https://github.com/Arkowne/vbc-computercraft) axée sur les performances.

## Différences vs l'original

| | Original | Cette version |
|---|---|---|
| Framework | Flask (sync) | FastAPI (async) |
| Conversion | Bloque le serveur | Background task, non-bloquant |
| Audio | 1 seul fichier DFPWM | Chunks de N secondes (configurable) |
| Format frames | JSON verbeux | Binaire compact (10× plus petit) |
| Cache | ❌ | ✅ Hash SHA256 (pas de reconversion) |
| Upload | Tout en RAM | Streaming par blocs |
| API | HTML uniquement | REST JSON + téléchargement binaire |

---

## Installation

### Prérequis
- Python 3.10+
- [FFmpeg](https://ffmpeg.org/) installé et dans le PATH

### Lancement
```bash
pip install -r requirements.txt
python server.py
```

Ouvre ensuite : `http://0.0.0.0:4334`

### Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `VBC_PORT` | `4334` | Port du serveur |
| `VBC_STORAGE` | `./videos` | Dossier de stockage |
| `VBC_FPS` | `10` | FPS cible (CC ≤ 20) |
| `VBC_AUDIO_CHUNK` | `5` | Durée chunks audio (secondes) |
| `VBC_FFMPEG_THREADS` | `0` (auto) | Threads FFmpeg |

---

## API

### Upload
```
POST /api/upload
Content-Type: multipart/form-data
  file: <fichier vidéo>
  name: <nom optionnel>

→ { "id": "a1b2c3d4", "status": "pending" }
```

### État de conversion (à poller)
```
GET /api/videos/{id}/status
→ { "id": "...", "status": "pending|processing|ready|error" }
```

### Liste des vidéos
```
GET /api/videos
→ [{ "id": ..., "width": 51, "height": 19, "fps": 10, ... }, ...]
```

### Télécharger les frames (tout d'un coup)
```
GET /api/videos/{id}/frames
→ binaire VBCF (voir format ci-dessous)
```

### Une frame spécifique (pour clients avec peu de RAM)
```
GET /api/videos/{id}/frame/{n}
→ { "width": 51, "height": 19, "pixels": [0,15,3,...] }
```

### Chunk audio DFPWM
```
GET /api/videos/{id}/audio/{chunk_index}
→ binaire DFPWM (48kHz mono)
```

---

## Format binaire VBCF (frames)

```
Header (12 bytes) :
  [4]  magic = "VBCF"
  [2]  width  (uint16 LE)
  [2]  height (uint16 LE)
  [4]  frame_count (uint32 LE)

Frames (frame_count blocs) :
  [width × height bytes] index couleur CC (0-15) par pixel
```

Les 16 couleurs CC sont indexées dans l'ordre standard ComputerCraft :
0=blanc, 1=orange, 2=magenta, 3=bleu clair, 4=jaune, 5=lime,
6=rose, 7=gris, 8=gris clair, 9=cyan, 10=violet, 11=bleu,
12=marron, 13=vert, 14=rouge, 15=noir

---

## Côté ComputerCraft (client Lua)

Le client doit :
1. `GET /api/videos` → choisir un id
2. `GET /api/videos/{id}/status` → attendre `"ready"`
3. `GET /api/videos/{id}/frames` → télécharger frames.bin
4. Parser le header VBCF, lire les frames une par une
5. `monitor.blit()` chaque frame (pixel par pixel)
6. En parallèle, poll les chunks audio : `GET /api/videos/{id}/audio/0`, `/audio/1`, ...
7. `speaker.playAudio()` chaque chunk DFPWM

> Le client Lua sera fait dans la prochaine étape du projet.
