from __future__ import annotations

import hashlib
import mimetypes
import os
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException, UploadFile

from app.config import settings


class UploadResult:
    def __init__(self, filename: str, stored_path: str, size_bytes: int, sha256: str, mime_type: str):
        self.filename = filename
        self.stored_path = stored_path
        self.size_bytes = size_bytes
        self.sha256 = sha256
        self.mime_type = mime_type


def _validate_extension(filename: str, allowed: Iterable[str]) -> None:
    lowered = filename.lower()
    if not any(lowered.endswith(ext) for ext in allowed):
        raise HTTPException(status_code=400, detail="File extension not allowed")


def _scan_clamav(path: Path) -> None:
    if not settings.clamav_enabled:
        return
    import socket

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(settings.clamav_socket)
        sock.sendall(f"SCAN {path}\n".encode())
        result = sock.recv(4096).decode()
        if "FOUND" in result:
            raise HTTPException(status_code=400, detail="Malware detected by ClamAV")


def save_upload(file: UploadFile, storage_dir: Path, allowed_exts: Iterable[str]) -> UploadResult:
    _validate_extension(file.filename, allowed_exts)
    storage_dir.mkdir(parents=True, exist_ok=True)
    filename = os.path.basename(file.filename)
    destination = storage_dir / f"{hashlib.sha256(filename.encode()).hexdigest()}-{filename}"
    max_bytes = settings.max_upload_mb * 1024 * 1024

    size = 0
    sha256 = hashlib.sha256()
    with destination.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="File too large")
            sha256.update(chunk)
            out.write(chunk)

    _scan_clamav(destination)
    mime_type, _ = mimetypes.guess_type(filename)
    return UploadResult(
        filename=filename,
        stored_path=str(destination),
        size_bytes=size,
        sha256=sha256.hexdigest(),
        mime_type=mime_type or "application/octet-stream",
    )
