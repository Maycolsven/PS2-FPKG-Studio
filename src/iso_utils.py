"""
iso_utils.py - Utilidades de lectura ISO9660, conversión BIN->ISO y validación de discos PS2.
"""

from __future__ import annotations

import math
import os
import re
import struct
from typing import BinaryIO

from .config_generator import get_game_config

SECTOR_SIZE = 2048
RAW_SECTOR_SIZE = 2352
PVD_SECTOR = 16
PVD_MAGIC_TYPE = 0x01
PVD_MAGIC_ID = b"CD001"
PVD_SYSTEM_ID_OFFSET = 8
PVD_SYSTEM_ID_LENGTH = 32
PVD_VOLUME_ID_OFFSET = 40
PVD_VOLUME_ID_LENGTH = 32
PVD_VOLUME_SIZE_OFFSET = 80
PVD_ROOT_DIR_RECORD_OFFSET = 156
PVD_ROOT_DIR_RECORD_LENGTH = 34
DIR_FLAG_DIRECTORY = 0x02
CD_SIZE_THRESHOLD = 700 * 1024 * 1024
MIN_ISO_SIZE = (PVD_SECTOR + 1) * SECTOR_SIZE

_GAME_ID_PATTERN = re.compile(
    r"BOOT2\s*=\s*cdrom0:\\?([A-Z]{4}[_-]\d{3}\.\d{2})",
    re.IGNORECASE,
)


def convert_bin_to_iso(bin_path: str, output_iso_path: str) -> str:
    """Convierte una imagen CD RAW (.bin/.img de 2352 bytes/sector) a ISO9660 (2048 bytes/sector)."""
    file_size = os.path.getsize(bin_path)
    if file_size % RAW_SECTOR_SIZE != 0:
        raise ValueError(f"El archivo '{bin_path}' no es múltiplo de {RAW_SECTOR_SIZE} bytes.")

    # Detectar offset de datos en el sector 16 (Mode 1 = 16 bytes header, Mode 2 Form 1 = 24 bytes header)
    with open(bin_path, "rb") as f:
        f.seek(PVD_SECTOR * RAW_SECTOR_SIZE)
        sector_16 = f.read(RAW_SECTOR_SIZE)
        if sector_16[24:30] == b"\x01CD001":
            data_offset = 24
        elif sector_16[16:22] == b"\x01CD001":
            data_offset = 16
        else:
            raise ValueError("No se encontró firma ISO9660 (CD001) en el archivo BIN.")

    total_sectors = file_size // RAW_SECTOR_SIZE
    os.makedirs(os.path.dirname(os.path.abspath(output_iso_path)), exist_ok=True)
    with open(bin_path, "rb") as src, open(output_iso_path, "wb") as dst:
        for _ in range(total_sectors):
            raw_sector = src.read(RAW_SECTOR_SIZE)
            if len(raw_sector) < data_offset + SECTOR_SIZE:
                break
            dst.write(raw_sector[data_offset : data_offset + SECTOR_SIZE])

    return os.path.abspath(output_iso_path)


class ISO9660Reader:
    def __init__(self, iso_path: str) -> None:
        self.iso_path: str = os.path.abspath(iso_path)
        if not os.path.isfile(self.iso_path):
            raise FileNotFoundError(f"No se encontró el archivo ISO: {self.iso_path}")
        self.file_size: int = os.path.getsize(self.iso_path)
        if self.file_size < MIN_ISO_SIZE:
            raise ValueError(f"Archivo demasiado pequeño ({self.file_size} bytes).")
        self._fh: BinaryIO = open(self.iso_path, "rb")
        self._pvd_cache: dict | None = None

    def close(self) -> None:
        if self._fh and not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> "ISO9660Reader":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def read_sector(self, sector: int, count: int = 1) -> bytes:
        offset = sector * SECTOR_SIZE
        length = count * SECTOR_SIZE
        if offset + length > self.file_size:
            raise IOError(f"Lectura fuera de rango: sector {sector}")
        self._fh.seek(offset)
        return self._fh.read(length)

    def get_primary_volume_descriptor(self) -> dict:
        if self._pvd_cache is not None:
            return self._pvd_cache
        pvd_data = self.read_sector(PVD_SECTOR)
        if pvd_data[0] != PVD_MAGIC_TYPE or pvd_data[1:6] != PVD_MAGIC_ID:
            raise ValueError("PVD ISO9660 inválido (no se encontró firma CD001).")

        system_id = pvd_data[PVD_SYSTEM_ID_OFFSET : PVD_SYSTEM_ID_OFFSET + PVD_SYSTEM_ID_LENGTH].decode("ascii", errors="replace").strip()
        volume_id = pvd_data[PVD_VOLUME_ID_OFFSET : PVD_VOLUME_ID_OFFSET + PVD_VOLUME_ID_LENGTH].decode("ascii", errors="replace").strip()
        volume_size = struct.unpack_from("<I", pvd_data, PVD_VOLUME_SIZE_OFFSET)[0]
        root_dir_record = pvd_data[PVD_ROOT_DIR_RECORD_OFFSET : PVD_ROOT_DIR_RECORD_OFFSET + PVD_ROOT_DIR_RECORD_LENGTH]

        self._pvd_cache = {
            "system_id": system_id,
            "volume_id": volume_id,
            "volume_size": volume_size,
            "root_dir_record": root_dir_record,
        }
        return self._pvd_cache

    def read_directory(self, record: bytes) -> list[dict]:
        dir_lba = struct.unpack_from("<I", record, 2)[0]
        dir_length = struct.unpack_from("<I", record, 10)[0]
        if dir_lba == 0 or dir_length == 0:
            return []

        sector_count = math.ceil(dir_length / SECTOR_SIZE)
        dir_data = self.read_sector(dir_lba, sector_count)
        entries: list[dict] = []
        offset = 0

        while offset < dir_length:
            rec_len = dir_data[offset]
            if rec_len == 0:
                next_sector_offset = ((offset // SECTOR_SIZE) + 1) * SECTOR_SIZE
                if next_sector_offset >= dir_length:
                    break
                offset = next_sector_offset
                continue
            if offset + rec_len > len(dir_data):
                break
            entry_raw = dir_data[offset : offset + rec_len]
            extent_lba = struct.unpack_from("<I", entry_raw, 2)[0]
            data_length = struct.unpack_from("<I", entry_raw, 10)[0]
            file_flags = entry_raw[25]
            is_directory = bool(file_flags & DIR_FLAG_DIRECTORY)
            name_length = entry_raw[32]
            raw_name = entry_raw[33 : 33 + name_length] if (name_length > 0 and 33 + name_length <= len(entry_raw)) else b""

            if raw_name in (b"\x00", b"\x01"):
                offset += rec_len
                continue

            name = _decode_directory_name(raw_name)
            entries.append({
                "name": name,
                "extent_lba": extent_lba,
                "data_length": data_length,
                "is_directory": is_directory,
                "raw": entry_raw,
            })
            offset += rec_len
        return entries

    def find_file(self, path: str) -> dict | None:
        parts = [p.upper() for p in path.replace("\\", "/").strip("/").split("/") if p]
        if not parts:
            return None
        current_record = self.get_primary_volume_descriptor()["root_dir_record"]
        for i, part in enumerate(parts):
            entries = self.read_directory(current_record)
            is_last = i == len(parts) - 1
            found = False
            for entry in entries:
                if entry["name"].upper() == part:
                    if is_last:
                        return entry
                    if entry["is_directory"]:
                        current_record = entry["raw"]
                        found = True
                        break
                    return None
            if not found and not is_last:
                return None
        return None

    def read_file(self, path: str) -> bytes:
        entry = self.find_file(path)
        if entry is None:
            raise FileNotFoundError(f"Archivo no encontrado en la ISO: {path!r}")
        if entry["data_length"] == 0:
            return b""
        sector_count = math.ceil(entry["data_length"] / SECTOR_SIZE)
        return self.read_sector(entry["extent_lba"], sector_count)[: entry["data_length"]]

    def list_root(self) -> list[str]:
        pvd = self.get_primary_volume_descriptor()
        return [e["name"] for e in self.read_directory(pvd["root_dir_record"])]


def _decode_directory_name(raw_name: bytes) -> str:
    name = raw_name.decode("ascii", errors="replace")
    if ";" in name:
        name = name.split(";")[0]
    return name.rstrip(".")


def _extract_game_id_from_system_cnf(data: bytes) -> str | None:
    text = data.decode("ascii", errors="replace")
    match = _GAME_ID_PATTERN.search(text)
    if match:
        raw = match.group(1).upper()
        return f"{raw[:4]}-{raw[5:].replace('.', '')}"
    return None


def validate_ps2_iso(iso_path: str) -> dict:
    errors: list[str] = []
    if not os.path.isfile(iso_path):
        return {"valid": False, "game_id": None, "title": None, "errors": [f"El archivo no existe: {iso_path}"], "file_size": 0, "disc_type": "DVD"}

    file_size = os.path.getsize(iso_path)
    disc_type = "CD" if file_size < CD_SIZE_THRESHOLD else "DVD"

    try:
        with ISO9660Reader(iso_path) as iso:
            pvd = iso.get_primary_volume_descriptor()
            vol_id = pvd.get("volume_id") or ""
            if iso.find_file("SYSTEM.CNF") is None:
                errors.append("No se encontró SYSTEM.CNF en la raíz de la ISO.")
                return {"valid": False, "game_id": None, "title": vol_id, "errors": errors, "file_size": file_size, "disc_type": disc_type}
            cnf_data = iso.read_file("SYSTEM.CNF")
            game_id = _extract_game_id_from_system_cnf(cnf_data)
            db_entry = get_game_config(game_id) if game_id else None
            title = (db_entry.get("title") if db_entry else None) or vol_id.replace("_", " ").title() or None
            return {"valid": True, "game_id": game_id, "title": title, "errors": errors, "file_size": file_size, "disc_type": disc_type}
    except Exception as e:
        errors.append(str(e))
        return {"valid": False, "game_id": None, "title": None, "errors": errors, "file_size": file_size, "disc_type": disc_type}


def get_iso_info(iso_path: str) -> dict:
    file_size = os.path.getsize(iso_path)
    disc_type = "CD" if file_size < CD_SIZE_THRESHOLD else "DVD"
    game_id: str | None = None

    with ISO9660Reader(iso_path) as iso:
        pvd = iso.get_primary_volume_descriptor()
        root_files = iso.list_root()
        try:
            cnf_data = iso.read_file("SYSTEM.CNF")
            game_id = _extract_game_id_from_system_cnf(cnf_data)
        except Exception:
            pass

    vol_id = pvd["volume_id"]
    db_entry = get_game_config(game_id) if game_id else None
    friendly_title = (
        db_entry["title"]
        if db_entry and db_entry.get("title")
        else (vol_id.replace("_", " ").strip().title() if vol_id else "")
    )

    return {
        "file_size": file_size,
        "game_id": game_id,
        "title": friendly_title,
        "disc_type": disc_type,
        "volume_id": vol_id,
        "system_id": pvd["system_id"],
        "root_files": root_files,
    }