"""
api/routes.py

Routes FastAPI :
  POST /api/upload          — upload + démarre la conversion en background
  GET  /api/videos          — liste toutes les vidéos
  GET  /api/videos/{id}     — métadonnées d'une vidéo
  GET  /api/videos/{id}/status  — état de conversion (pending/processing/ready/error)
  GET  /api/videos/{id}/frames  — télécharge tout le fichier frames.bin
  GET  /api/videos/{id}/frame/{n}  — une frame spécifique (pour preview)
  GET  /api/videos/{id}/audio/{chunk}  — chunk audio DFPWM
  DELETE /api/videos/{id}   — supprime une vidéo
"""

import asyncio
import struct
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from core.config import settings
from core.converter import convert_video
from storage.manager import storage_manager

router = APIRouter(prefix="/api")

# Suivi des conversions en cours : video_id → "pending" | "processing" | "ready" | "error"
_conversion_status: dict[str, str] = {}
_conversion_errors: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    name: Annotated[str, Form()] = "",
):
    """
    Upload une vidéo et démarre la conversion en arrière-plan.
    Retourne immédiatement un video_id, sans attendre la fin de conversion.
    """
    # Vérifie le type
    allowed = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"Format non supporté. Acceptés : {', '.join(allowed)}")

    video_id = storage_manager.new_video_id()
    video_dir = storage_manager.video_dir(video_id)
    source_path = video_dir / f"source{suffix}"

    # Sauvegarde le fichier uploadé (streaming pour ne pas tout garder en RAM)
    total = 0
    with open(source_path, "wb") as f:
        while chunk := await file.read(1024 * 64):
            total += len(chunk)
            if total > settings.MAX_UPLOAD_SIZE:
                source_path.unlink(missing_ok=True)
                raise HTTPException(413, "Fichier trop grand (max 500MB)")
            f.write(chunk)

    # Stocke le nom dans les métadonnées temporaires
    (video_dir / "meta.json").write_text(
        f'{{"id": "{video_id}", "name": "{name or file.filename}", "status": "pending"}}'
    )

    _conversion_status[video_id] = "pending"
    background_tasks.add_task(_run_conversion, video_id, source_path)

    return {"id": video_id, "status": "pending"}


async def _run_conversion(video_id: str, source_path: Path):
    _conversion_status[video_id] = "processing"
    try:
        meta = await convert_video(video_id, source_path)
        meta["status"] = "ready"
        _conversion_status[video_id] = "ready"
        # Met à jour meta.json avec le statut final
        (storage_manager.video_dir(video_id) / "meta.json").write_text(
            __import__("json").dumps(meta, indent=2)
        )
    except Exception as e:
        _conversion_status[video_id] = "error"
        _conversion_errors[video_id] = str(e)


# ---------------------------------------------------------------------------
# Vidéos
# ---------------------------------------------------------------------------


@router.get("/videos")
def list_videos():
    videos = storage_manager.list_videos()
    # Enrichit avec le statut live si conversion en cours
    for v in videos:
        vid = v.get("id", "")
        if vid in _conversion_status:
            v["status"] = _conversion_status[vid]
    return videos


@router.get("/videos/{video_id}")
def get_video(video_id: str):
    meta = storage_manager.get_meta(video_id)
    if not meta:
        raise HTTPException(404, "Vidéo introuvable")
    if video_id in _conversion_status:
        meta["status"] = _conversion_status[video_id]
    return meta


@router.get("/videos/{video_id}/status")
def get_status(video_id: str):
    """Endpoint léger pour que le client CC poll l'état de conversion."""
    status = _conversion_status.get(video_id)
    if status is None:
        meta = storage_manager.get_meta(video_id)
        if not meta:
            raise HTTPException(404, "Vidéo introuvable")
        status = meta.get("status", "ready")
    result = {"id": video_id, "status": status}
    if status == "error":
        result["error"] = _conversion_errors.get(video_id, "Erreur inconnue")
    return result


@router.delete("/videos/{video_id}")
def delete_video(video_id: str):
    if not storage_manager.delete_video(video_id):
        raise HTTPException(404, "Vidéo introuvable")
    _conversion_status.pop(video_id, None)
    _conversion_errors.pop(video_id, None)
    return {"deleted": video_id}


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------


@router.get("/videos/{video_id}/frames")
def get_frames(video_id: str):
    """
    Retourne tout le fichier frames.bin.
    Le client CC télécharge ça une fois et rejoue localement.
    
    Utilisé pour les petites vidéos (faible RAM requise).
    Pour les grandes vidéos, utilise /frames/{n} en streaming.
    """
    path = storage_manager.frames_path(video_id)
    if not path.exists():
        raise HTTPException(404, "Frames non disponibles (conversion en cours ?)")
    return FileResponse(path, media_type="application/octet-stream")


@router.get("/videos/{video_id}/frame/{frame_index}")
def get_single_frame(video_id: str, frame_index: int):
    """
    Retourne une frame individuelle en JSON (liste d'indices CC 0-15).
    Utile pour la preview web et pour les clients CC avec peu de RAM.
    
    Format réponse : {"width": W, "height": H, "pixels": [0,15,3,...]}
    """
    path = storage_manager.frames_path(video_id)
    if not path.exists():
        raise HTTPException(404, "Frames non disponibles")

    with open(path, "rb") as f:
        magic = f.read(4)
        if magic != b"VBCF":
            raise HTTPException(500, "Fichier frames corrompu")
        width, height, frame_count = struct.unpack("<HHI", f.read(8))

        if frame_index < 0 or frame_index >= frame_count:
            raise HTTPException(404, f"Frame {frame_index} inexistante (total: {frame_count})")

        pixel_count = width * height
        f.seek(12 + frame_index * pixel_count)
        pixels = list(f.read(pixel_count))

    return {"width": width, "height": height, "frame_index": frame_index, "pixels": pixels}


@router.get("/videos/{video_id}/frames/stream")
async def stream_frames(video_id: str):
    """
    Streaming des frames une par une via Server-Sent Events (SSE).
    
    Alternative pour clients avec peu de RAM :
    reçoit et affiche chaque frame dès qu'elle arrive, sans tout stocker.
    
    Format SSE : data: <JSON frame>\\n\\n
    """
    path = storage_manager.frames_path(video_id)
    if not path.exists():
        raise HTTPException(404, "Frames non disponibles")

    async def generate():
        meta = storage_manager.get_meta(video_id)
        fps = meta.get("fps", 10) if meta else 10
        frame_interval = 1.0 / fps

        with open(path, "rb") as f:
            magic = f.read(4)
            if magic != b"VBCF":
                return
            width, height, frame_count = struct.unpack("<HHI", f.read(8))
            pixel_count = width * height

            for i in range(frame_count):
                pixels = list(f.read(pixel_count))
                data = __import__("json").dumps({
                    "i": i,
                    "w": width,
                    "h": height,
                    "p": pixels,
                    "total": frame_count,
                })
                yield f"data: {data}\n\n"
                await asyncio.sleep(frame_interval)

        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------


@router.get("/videos/{video_id}/audio/{chunk_index}")
def get_audio_chunk(video_id: str, chunk_index: int):
    """
    Retourne un chunk audio DFPWM.
    
    Le client CC télécharge les chunks au fur et à mesure pendant la lecture,
    ce qui évite les crashes mémoire sur les longues vidéos.
    """
    path = storage_manager.audio_chunk_path(video_id, chunk_index)
    if not path.exists():
        raise HTTPException(404, f"Chunk audio {chunk_index} introuvable")
    return FileResponse(path, media_type="application/octet-stream")
