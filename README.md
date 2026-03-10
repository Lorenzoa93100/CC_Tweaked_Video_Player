# 🎬 CC_Tweaked_Video_Player

> Joue des vidéos sur des monitors [ComputerCraft: Tweaked](https://tweaked.cc/) en Minecraft.

Un serveur Python (FastAPI) convertit tes vidéos en frames de pixels CC + audio DFPWM, et un client Lua les joue directement sur un monitor avec speaker.

---

## ✨ Différences avec le projet original

| | [vbc-computercraft](https://github.com/Arkowne/vbc-computercraft) | Ce projet |
|---|---|---|
| Framework serveur | Flask (sync) | FastAPI (async) |
| Conversion | Bloque le serveur | Background task non-bloquant |
| Format frames | JSON | Binaire compact VBCF (10× plus léger) |
| Audio | 1 seul fichier DFPWM | Chunks de N secondes (pas de crash mémoire) |
| Cache | ❌ | ✅ Hash SHA256 (pas de reconversion inutile) |
| Upload | Tout en RAM | Streaming par blocs |
| Sync A/V | Approximative | Basée sur `os.clock()` avec saut de frames |

---

## 🧰 Prérequis serveur

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/) installé et dans le PATH

## 🖥️ Lancement du serveur

```bash
pip install -r requirements.txt
python server.py
```

Ouvre ensuite `http://ton_ip:4334` pour uploader des vidéos.

### Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `VBC_PORT` | `4334` | Port du serveur |
| `VBC_STORAGE` | `./videos` | Dossier de stockage |
| `VBC_FPS` | `10` | FPS cible |
| `VBC_AUDIO_CHUNK` | `5` | Durée des chunks audio (secondes) |
| `VBC_FFMPEG_THREADS` | `0` (auto) | Threads FFmpeg |

---

## ⚙️ Installation côté ComputerCraft

1. Configure l'adresse du serveur :
```
set vbc.server http://ton_ip:4334
```

2. Lance l'installateur :
```
wget run http://ton_ip:4334/api/install
```

3. Attache un **Advanced Monitor** et un **Speaker** à ton ordinateur.

> ⚠️ L'API HTTP doit être activée dans la config ComputerCraft si tu utilises une IP locale (`http://`).

---

## ▶️ Commandes

```
vbc list              — Liste les vidéos disponibles sur le serveur
vbc play <id>         — Joue une vidéo
vbc play <id> no      — Joue sans audio
vbc info <id>         — Affiche les infos d'une vidéo
```

Appuie sur `Q` pendant la lecture pour arrêter.

---

## 📁 Structure du projet

```
├── server_files/
│   ├── server.py          — Point d'entrée FastAPI
│   ├── core/
│   │   ├── config.py      — Configuration (env vars)
│   │   └── converter.py   — Conversion FFmpeg → VBCF + DFPWM
│   ├── api/
│   │   ├── routes.py      — Routes API (upload, frames, audio...)
│   │   └── client_routes.py — Distribution des fichiers Lua
│   └── storage/
│       └── manager.py     — Gestion des fichiers sur disque
│
└── client_files/
    ├── vbc.lua            — Point d'entrée (commandes)
    ├── player.lua         — Lecture vidéo + audio en parallèle
    ├── frames.lua         — Décodage VBCF + rendu blit
    ├── net.lua            — Requêtes HTTP
    ├── config.lua         — Lecture des settings CC
    ├── ui.lua             — Affichage terminal
    └── install.lua        — Script d'installation
```

---

## 📦 Format binaire VBCF

Les frames sont stockées dans un format binaire custom plutôt qu'en JSON, ce qui les rend ~10× plus légères à télécharger et à parser côté CC.

```
Header (12 bytes) :
  [4]  magic "VBCF"
  [2]  width  (uint16 LE)
  [2]  height (uint16 LE)
  [4]  frame_count (uint32 LE)

Frames :
  frame_count × (width × height bytes)
  chaque byte = index couleur CC (0–15)
```

---

## 📝 License

[MIT](LICENSE)
