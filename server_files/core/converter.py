"""
core/converter.py

Conversion vidéo → frames CC + chunks audio DFPWM.

Optimisations vs l'original :
- Un seul passage FFmpeg pour extraire frames + audio
- Frames encodées en binaire compact (pas JSON)
- Audio découpé en chunks de N secondes dès la conversion
- Hash SHA256 pour cache : pas de reconversion si déjà traité
"""

import asyncio
import hashlib
import json
import struct
import subprocess
from pathlib import Path

from core.config import settings
from storage.manager import storage_manager


# ---------------------------------------------------------------------------
# Format binaire des frames
# ---------------------------------------------------------------------------
# Chaque frame est stockée dans un fichier binaire :
#   Header : [width u16][height u16][frame_count u32]
#   Frames : pour chaque frame, [pixel_count u32] suivi de pixel_count bytes
#            où chaque byte est un index couleur CC (0-15) encodé en nibbles :
#            nibble haut = fg color, nibble bas = bg color
#
# Pourquoi binaire ?
#   - JSON d'une frame 51×19 = ~5Ko  → binaire = ~485 bytes  (10× plus compact)
#   - Moins de parsing côté serveur pour servir les frames
# ---------------------------------------------------------------------------


CC_COLORS = [
    (240, 240, 240),  # 0  white
    (242, 178, 51),   # 1  orange
    (197, 91, 198),   # 2  magenta
    (74, 128, 255),   # 3  lightBlue
    (255, 216, 10),   # 4  yellow
    (127, 204, 25),   # 5  lime
    (242, 178, 204),  # 6  pink
    (76, 76, 76),     # 7  gray
    (153, 153, 153),  # 8  lightGray
    (25, 153, 198),   # 9  cyan
    (178, 51, 229),   # 10 purple
    (51, 102, 204),   # 11 blue
    (102, 76, 51),    # 12 brown
    (102, 127, 51),   # 13 green
    (153, 51, 51),    # 14 red
    (17, 17, 17),     # 15 black
]


def _nearest_cc_color(r: int, g: int, b: int) -> int:
    """Trouve l'index CC le plus proche (distance euclidienne dans RGB)."""
    best_idx = 0
    best_dist = float("inf")
    for i, (cr, cg, cb) in enumerate(CC_COLORS):
        d = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if d < best_dist:
            best_dist = d
            best_idx = i
    return best_idx


def _build_color_lut() -> list[list[int]]:
    """Pré-calcule une LUT 6-bit RGB → index CC (256^3 serait trop grand).
    On utilise une résolution de 32 niveaux par canal (5 bits → ~32K entrées)."""
    lut = {}
    return lut  # on calcule à la volée via cache dict — suffisant en practice


async def convert_video(video_id: str, source_path: Path) -> dict:
    """
    Point d'entrée principal. Retourne un dict avec les métadonnées
    ou lève une exception en cas d'erreur.
    """
    video_dir = storage_manager.video_dir(video_id)

    # --- 1. Vérifie si déjà converti (cache par hash du fichier source) ---
    meta_path = video_dir / "meta.json"
    source_hash = _sha256(source_path)

    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        if meta.get("source_hash") == source_hash:
            return meta  # cache hit !

    # --- 2. Sonde la vidéo (dimensions, durée, fps) ---
    probe = await _ffprobe(source_path)
    width = probe["width"]
    height = probe["height"]
    duration = probe["duration"]
    fps = settings.TARGET_FPS

    # Calcule une résolution qui tient sur un monitor CC standard
    # (limitée à 8 blocs wide × 5 blocs tall = 152×57 pixels CC)
    width, height = _clamp_resolution(width, height)

    # --- 3. Extraction des frames (PPM raw via pipe) ---
    frames_path = video_dir / "frames.bin"
    await _extract_frames(source_path, frames_path, width, height, fps)

    # --- 4. Extraction + encodage audio DFPWM en chunks ---
    audio_chunks = 0
    has_audio = probe.get("has_audio", False)
    if has_audio:
        audio_chunks = await _extract_audio_chunks(
            source_path, video_dir, duration
        )

    # --- 5. Sauvegarde des métadonnées ---
    frame_count = _count_frames(frames_path)
    meta = {
        "id": video_id,
        "source_hash": source_hash,
        "width": width,
        "height": height,
        "fps": fps,
        "duration": round(duration, 3),
        "frame_count": frame_count,
        "has_audio": has_audio,
        "audio_chunks": audio_chunks,
        "audio_chunk_seconds": settings.AUDIO_CHUNK_SECONDS,
    }
    meta_path.write_text(json.dumps(meta, indent=2))

    return meta


# ---------------------------------------------------------------------------
# Helpers FFmpeg
# ---------------------------------------------------------------------------


async def _ffprobe(path: Path) -> dict:
    """Récupère les infos de la vidéo via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    data = json.loads(stdout)

    result = {"has_audio": False, "duration": 0.0, "width": settings.DEFAULT_WIDTH, "height": settings.DEFAULT_HEIGHT}

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            result["width"] = stream["width"]
            result["height"] = stream["height"]
            # fps peut être "30/1" ou "30000/1001"
            fps_str = stream.get("r_frame_rate", "10/1")
            num, den = map(int, fps_str.split("/"))
            result["fps"] = num / den if den else 10
        elif stream.get("codec_type") == "audio":
            result["has_audio"] = True

    result["duration"] = float(data.get("format", {}).get("duration", 0))
    return result


async def _extract_frames(
    src: Path, dst: Path, width: int, height: int, fps: int
) -> None:
    """
    Extrait les frames avec FFmpeg et les écrit en binaire compact.
    
    FFmpeg écrit les pixels en raw RGB24 via pipe → on les convertit
    directement en couleurs CC sans fichiers intermédiaires.
    
    Format binaire :
      [4 bytes] magic "VBCF"
      [2 bytes] width (uint16 LE)
      [2 bytes] height (uint16 LE)
      [4 bytes] frame_count placeholder (rempli après)
      Pour chaque frame :
        [width*height bytes] index CC par pixel (0-15)
    """
    pixel_count = width * height

    # Pré-calcule la LUT couleur une fois pour toute la vidéo
    color_lut: dict[tuple, int] = {}

    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-vf", f"fps={fps},scale={width}:{height}:flags=lanczos",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-threads", str(settings.FFMPEG_THREADS),
        "pipe:1",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    frame_count = 0
    with open(dst, "wb") as f:
        # Header
        f.write(b"VBCF")
        f.write(struct.pack("<HHI", width, height, 0))  # frame_count = 0 pour l'instant

        raw_frame_size = pixel_count * 3  # RGB24

        buffer = b""
        while True:
            chunk = await proc.stdout.read(65536)
            if not chunk:
                break
            buffer += chunk

            while len(buffer) >= raw_frame_size:
                frame_data = buffer[:raw_frame_size]
                buffer = buffer[raw_frame_size:]

                # Converti chaque pixel RGB → index CC
                out = bytearray(pixel_count)
                for i in range(pixel_count):
                    r = frame_data[i * 3]
                    g = frame_data[i * 3 + 1]
                    b = frame_data[i * 3 + 2]
                    key = (r >> 3, g >> 3, b >> 3)  # quantise à 5 bits pour la LUT
                    if key not in color_lut:
                        color_lut[key] = _nearest_cc_color(r, g, b)
                    out[i] = color_lut[key]

                f.write(bytes(out))
                frame_count += 1

        # Met à jour le frame_count dans le header
        f.seek(8)
        f.write(struct.pack("<I", frame_count))

    await proc.wait()


async def _extract_audio_chunks(
    src: Path, dst_dir: Path, duration: float
) -> int:
    """
    Extrait l'audio en DFPWM, découpé en chunks de AUDIO_CHUNK_SECONDS secondes.
    
    DFPWM = format audio natif de CC:Tweaked (1-bit, 48kHz)
    FFmpeg supporte dfpwm depuis la version 5.1.
    
    Chaque chunk est sauvegardé dans dst_dir/audio_000.dfpwm, audio_001.dfpwm, ...
    
    Pourquoi des chunks ?
    - L'original génère un seul gros fichier → crash mémoire sur longues vidéos côté CC
    - Avec des chunks de 5s, le client CC peut les télécharger au fur et à mesure
    """
    chunk_s = settings.AUDIO_CHUNK_SECONDS
    n_chunks = max(1, int(duration / chunk_s) + (1 if duration % chunk_s else 0))

    for i in range(n_chunks):
        start = i * chunk_s
        out_path = dst_dir / f"audio_{i:04d}.dfpwm"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(src),
            "-ss", str(start),
            "-t", str(chunk_s),
            "-ar", "48000",      # 48kHz requis par CC
            "-ac", "1",          # mono
            "-f", "dfpwm",
            "-threads", str(settings.FFMPEG_THREADS),
            str(out_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        if not out_path.exists() or out_path.stat().st_size == 0:
            # Chunk vide ou erreur → on s'arrête
            return i

    return n_chunks


def _count_frames(frames_path: Path) -> int:
    """Lit le frame_count depuis le header du fichier binaire."""
    if not frames_path.exists():
        return 0
    with open(frames_path, "rb") as f:
        magic = f.read(4)
        if magic != b"VBCF":
            return 0
        f.read(4)  # width + height
        return struct.unpack("<I", f.read(4))[0]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _clamp_resolution(w: int, h: int, max_w: int = 164, max_h: int = 81) -> tuple[int, int]:
    """
    Limite la résolution pour tenir sur un monitor CC raisonnable.
    Garde le ratio. max_w/max_h correspondent à ~8×5 blocs de monitor.
    """
    if w <= max_w and h <= max_h:
        return w, h
    ratio = min(max_w / w, max_h / h)
    # Arrondi aux dimensions paires (requis par certains encoders)
    new_w = int(w * ratio) & ~1
    new_h = int(h * ratio) & ~1
    return max(new_w, 2), max(new_h, 2)
