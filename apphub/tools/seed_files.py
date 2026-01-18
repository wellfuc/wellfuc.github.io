import os
from pathlib import Path

from app.config import settings


def main() -> None:
    storage_files = Path(settings.storage_root) / "files"
    storage_media = Path(settings.storage_root) / "media"
    storage_files.mkdir(parents=True, exist_ok=True)
    storage_media.mkdir(parents=True, exist_ok=True)

    for name in ["launchpad-setup.exe", "ledgerdesk-setup.exe", "fleet-ops-setup.exe"]:
        path = storage_files / name
        if not path.exists():
            path.write_bytes(os.urandom(1024))

    for name in ["launchpad-hero.png", "ledgerdesk-hero.png", "fleet-ops-hero.png"]:
        path = storage_media / name
        if not path.exists():
            path.write_bytes(os.urandom(2048))


if __name__ == "__main__":
    main()
