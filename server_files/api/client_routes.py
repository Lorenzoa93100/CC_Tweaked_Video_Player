"""
api/client_routes.py

Routes pour distribuer les fichiers du client Lua directement depuis le serveur.
Ça permet d'installer le client avec un simple :
  wget run http://<ip>:4334/api/install

Routes :
  GET /api/install         → install.lua (script d'installation)
  GET /api/client/<file>   → fichiers individuels du client Lua
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

router = APIRouter(prefix="/api")

# Dossier contenant les fichiers Lua du client
CLIENT_DIR = Path(__file__).parent.parent / "client_files"

# Fichiers autorisés à être servis
ALLOWED_FILES = {
    "vbc.lua",
    "config.lua",
    "net.lua",
    "frames.lua",
    "player.lua",
    "ui.lua",
    "install.lua",
}


@router.get("/install")
def get_installer():
    """Sert le script d'installation Lua."""
    path = CLIENT_DIR / "install.lua"
    if not path.exists():
        raise HTTPException(500, "Fichier install.lua manquant sur le serveur")
    return FileResponse(path, media_type="text/plain", filename="install.lua")


@router.get("/client/{filename}")
def get_client_file(filename: str):
    """Sert un fichier du client Lua."""
    if filename not in ALLOWED_FILES:
        raise HTTPException(404, f"Fichier '{filename}' inconnu")
    path = CLIENT_DIR / filename
    if not path.exists():
        raise HTTPException(500, f"Fichier '{filename}' manquant sur le serveur")
    return FileResponse(path, media_type="text/plain", filename=filename)
