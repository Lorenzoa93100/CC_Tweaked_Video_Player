"""
storage/manager.py

Gère la persistance des vidéos converties sur disque.
Structure :
  videos/
    <video_id>/
      source.<ext>     — fichier original uploadé
      meta.json        — métadonnées (résolution, fps, durée...)
      frames.bin       — frames CC en binaire compact
      audio_0000.dfpwm — chunk audio 0
      audio_0001.dfpwm — chunk audio 1
      ...
"""

import json
import uuid
from pathlib import Path

from core.config import settings


class StorageManager:
    def init_dirs(self):
        settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    def new_video_id(self) -> str:
        return uuid.uuid4().hex[:8]

    def video_dir(self, video_id: str) -> Path:
        d = settings.STORAGE_DIR / video_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def list_videos(self) -> list[dict]:
        videos = []
        for d in sorted(settings.STORAGE_DIR.iterdir()):
            meta_path = d / "meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    videos.append(meta)
                except Exception:
                    pass
        return videos

    def get_meta(self, video_id: str) -> dict | None:
        meta_path = settings.STORAGE_DIR / video_id / "meta.json"
        if not meta_path.exists():
            return None
        return json.loads(meta_path.read_text())

    def frames_path(self, video_id: str) -> Path:
        return settings.STORAGE_DIR / video_id / "frames.bin"

    def audio_chunk_path(self, video_id: str, chunk_index: int) -> Path:
        return settings.STORAGE_DIR / video_id / f"audio_{chunk_index:04d}.dfpwm"

    def delete_video(self, video_id: str) -> bool:
        import shutil
        d = settings.STORAGE_DIR / video_id
        if d.exists():
            shutil.rmtree(d)
            return True
        return False


storage_manager = StorageManager()
