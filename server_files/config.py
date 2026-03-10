import os
from pathlib import Path


class Settings:
    PORT: int = int(os.getenv("VBC_PORT", 4334))
    STORAGE_DIR: Path = Path(os.getenv("VBC_STORAGE", "./videos"))

    # Taille max d'upload (500MB)
    MAX_UPLOAD_SIZE: int = 500 * 1024 * 1024

    # Taille des chunks audio DFPWM (en secondes)
    # Plus petit = moins de RAM côté CC, mais plus de requêtes
    AUDIO_CHUNK_SECONDS: int = int(os.getenv("VBC_AUDIO_CHUNK", 5))

    # Résolution par défaut si non détectée
    DEFAULT_WIDTH: int = 51
    DEFAULT_HEIGHT: int = 19

    # FPS cible (CC peut difficilement dépasser 20)
    TARGET_FPS: int = int(os.getenv("VBC_FPS", 10))

    # Nb de threads FFmpeg (0 = auto)
    FFMPEG_THREADS: int = int(os.getenv("VBC_FFMPEG_THREADS", 0))


settings = Settings()
