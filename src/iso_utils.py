"""
iso_utils.py - Utilidades de lectura ISO9660 y validación de discos PS2.

Este módulo proporciona herramientas para leer imágenes ISO9660 y validar
que correspondan a discos de PlayStation 2, como parte de un conversor
PS2-a-PS4 (ISO → PKG).

Clases:
    ISO9660Reader: Lector de imágenes ISO9660 con soporte completo de
                   navegación de directorios y lectura de archivos.

Funciones:
    validate_ps2_iso: Valida que un archivo ISO sea un disco PS2 válido.
    get_iso_info: Obtiene información detallada de una imagen ISO.
"""

from __future__ import annotations

import math
import os
import re
import struct
from typing import BinaryIO

# =============================================================================
# Constantes del formato ISO9660
# =============================================================================

SECTOR_SIZE = 2048
"""Tamaño de un sector ISO9660 en bytes."""

PVD_SECTOR = 16
"""Sector donde se ubica el Primary Volume Descriptor."""

PVD_OFFSET = PVD_SECTOR * SECTOR_SIZE
"""Offset en bytes del PVD dentro de la imagen ISO (0x8000)."""

PVD_MAGIC_TYPE = 0x01
"""Byte de tipo esperado en el PVD."""

PVD_MAGIC_ID = b"CD001"
"""Identificador estándar ISO9660 en el PVD (bytes 1-5)."""

PVD_SYSTEM_ID_OFFSET = 8
"""Offset del System Identifier dentro del PVD."""

PVD_SYSTEM_ID_LENGTH = 32
"""Longitud del System Identifier en el PVD."""

PVD_VOLUME_ID_OFFSET = 40
"""Offset del Volume Identifier dentro del PVD."""

PVD_VOLUME_ID_LENGTH = 32
"""Longitud del Volume Identifier en el PVD."""

PVD_VOLUME_SIZE_OFFSET = 80
"""Offset del tamaño del volumen (both-endian uint32) en el PVD."""

PVD_ROOT_DIR_RECORD_OFFSET = 156
"""Offset del registro de directorio raíz dentro del PVD."""

PVD_ROOT_DIR_RECORD_LENGTH = 34
"""Longitud del registro de directorio raíz en el PVD."""

DIR_FLAG_DIRECTORY = 0x02
"""Bit de bandera que indica que un registro es un directorio."""

CD_SIZE_THRESHOLD = 700 * 1024 * 1024
"""Umbral de tamaño para distinguir CD (<700 MB) de DVD."""

# Tamaño mínimo razonable para una ISO (debe contener al menos el PVD)
MIN_ISO_SIZE = (PVD_SECTOR + 1) * SECTOR_SIZE

# Extensión de archivo BIN/CUE (para detección y advertencia)
BIN_CUE_EXTENSIONS = {".bin", ".cue"}

# Patrón para extraer el game ID del SYSTEM.CNF de PS2
# Ejemplo de línea: BOOT2 = cdrom0:\SLUS_200.01;1
_GAME_ID_PATTERN = re.compile(
    r"BOOT2\s*=\s*cdrom0:\\([A-Z]{4}_\d{3}\.\d{2})",
    re.IGNORECASE,
)


# =============================================================================
# Clase ISO9660Reader
# =============================================================================


class ISO9660Reader:
    """Lector de imágenes ISO9660 con navegación de directorios y lectura de archivos.

    Soporta uso como context manager::

        with ISO9660Reader("game.iso") as iso:
            pvd = iso.get_primary_volume_descriptor()
            files = iso.list_root()

    Attributes:
        iso_path: Ruta absoluta al archivo ISO.
        file_size: Tamaño en bytes del archivo ISO.
    """

    # -------------------------------------------------------------------------
    # Ciclo de vida
    # -------------------------------------------------------------------------

    def __init__(self, iso_path: str) -> None:
        """Abre el archivo ISO para lectura binaria.

        Args:
            iso_path: Ruta al archivo de imagen ISO9660.

        Raises:
            FileNotFoundError: Si el archivo no existe.
            PermissionError: Si no se tienen permisos de lectura.
            ValueError: Si el archivo es demasiado pequeño para ser una ISO válida.
        """
        self.iso_path: str = os.path.abspath(iso_path)

        if not os.path.isfile(self.iso_path):
            raise FileNotFoundError(f"No se encontró el archivo ISO: {self.iso_path}")

        self.file_size: int = os.path.getsize(self.iso_path)
        if self.file_size < MIN_ISO_SIZE:
            raise ValueError(
                f"El archivo es demasiado pequeño para ser una ISO válida "
                f"({self.file_size} bytes, mínimo esperado {MIN_ISO_SIZE} bytes)."
            )

        self._fh: BinaryIO = open(self.iso_path, "rb")  # noqa: SIM115
        self._pvd_cache: dict | None = None

    def close(self) -> None:
        """Cierra el handle del archivo ISO."""
        if self._fh and not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> "ISO9660Reader":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        self.close()

    # -------------------------------------------------------------------------
    # Lectura de bajo nivel
    # -------------------------------------------------------------------------

    def read_sector(self, sector: int, count: int = 1) -> bytes:
        """Lee uno o más sectores consecutivos de la imagen ISO.

        Args:
            sector: Número de sector inicial (0-based).
            count: Cantidad de sectores a leer (por defecto 1).

        Returns:
            Contenido crudo de los sectores solicitados.

        Raises:
            ValueError: Si *sector* o *count* son negativos.
            IOError: Si la lectura excede el tamaño del archivo.
        """
        if sector < 0:
            raise ValueError(f"El número de sector no puede ser negativo: {sector}")
        if count < 1:
            raise ValueError(f"La cantidad de sectores debe ser >= 1: {count}")

        offset = sector * SECTOR_SIZE
        length = count * SECTOR_SIZE

        if offset + length > self.file_size:
            raise IOError(
                f"Lectura fuera de rango: sector {sector}, count {count} "
                f"(offset {offset:#x}+{length:#x} > tamaño {self.file_size:#x})."
            )

        self._fh.seek(offset)
        data = self._fh.read(length)

        if len(data) != length:
            raise IOError(
                f"Lectura incompleta: se esperaban {length} bytes, "
                f"se obtuvieron {len(data)}."
            )

        return data

    # -------------------------------------------------------------------------
    # Primary Volume Descriptor
    # -------------------------------------------------------------------------

    def get_primary_volume_descriptor(self) -> dict:
        """Lee y parsea el Primary Volume Descriptor (PVD) en el sector 16.

        Returns:
            Diccionario con las claves:
                - ``system_id`` (str): Identificador del sistema.
                - ``volume_id`` (str): Identificador del volumen.
                - ``volume_size`` (int): Tamaño del volumen en sectores.
                - ``root_dir_record`` (bytes): Registro crudo del directorio raíz (34 bytes).

        Raises:
            ValueError: Si el PVD no contiene la firma ISO9660 esperada.
        """
        # Devolver cache si ya se leyó previamente
        if self._pvd_cache is not None:
            return self._pvd_cache

        pvd_data = self.read_sector(PVD_SECTOR)

        # Validar firma
        if pvd_data[0] != PVD_MAGIC_TYPE:
            raise ValueError(
                f"Tipo de descriptor inválido: se esperaba {PVD_MAGIC_TYPE:#04x}, "
                f"se obtuvo {pvd_data[0]:#04x}."
            )

        magic_id = pvd_data[1:6]
        if magic_id != PVD_MAGIC_ID:
            raise ValueError(
                f"Identificador ISO9660 inválido: se esperaba {PVD_MAGIC_ID!r}, "
                f"se obtuvo {magic_id!r}."
            )

        # Parsear campos
        system_id = pvd_data[
            PVD_SYSTEM_ID_OFFSET : PVD_SYSTEM_ID_OFFSET + PVD_SYSTEM_ID_LENGTH
        ].decode("ascii", errors="replace").strip()

        volume_id = pvd_data[
            PVD_VOLUME_ID_OFFSET : PVD_VOLUME_ID_OFFSET + PVD_VOLUME_ID_LENGTH
        ].decode("ascii", errors="replace").strip()

        # Tamaño del volumen: uint32 LE en both-endian (LE en los primeros 4 bytes)
        volume_size = struct.unpack_from("<I", pvd_data, PVD_VOLUME_SIZE_OFFSET)[0]

        root_dir_record = pvd_data[
            PVD_ROOT_DIR_RECORD_OFFSET : PVD_ROOT_DIR_RECORD_OFFSET
            + PVD_ROOT_DIR_RECORD_LENGTH
        ]

        self._pvd_cache = {
            "system_id": system_id,
            "volume_id": volume_id,
            "volume_size": volume_size,
            "root_dir_record": root_dir_record,
        }
        return self._pvd_cache

    # -------------------------------------------------------------------------
    # Directorios
    # -------------------------------------------------------------------------

    def read_directory(self, record: bytes) -> list[dict]:
        """Parsea las entradas de un directorio ISO9660 a partir de su registro.

        Lee el extent apuntado por *record* y decodifica cada entrada
        de directorio contenida en él.

        Args:
            record: Registro de directorio crudo (al menos 34 bytes) que
                    contiene el LBA y tamaño del directorio.

        Returns:
            Lista de diccionarios, cada uno con:
                - ``name`` (str): Nombre del archivo o directorio.
                - ``extent_lba`` (int): Sector de inicio del contenido.
                - ``data_length`` (int): Tamaño en bytes del contenido.
                - ``is_directory`` (bool): ``True`` si es un directorio.
                - ``raw`` (bytes): Registro crudo de la entrada.

        Raises:
            ValueError: Si *record* es demasiado corto.
        """
        if len(record) < PVD_ROOT_DIR_RECORD_LENGTH:
            raise ValueError(
                f"Registro de directorio demasiado corto: {len(record)} bytes "
                f"(mínimo {PVD_ROOT_DIR_RECORD_LENGTH})."
            )

        # Extraer ubicación y tamaño del directorio desde el registro padre
        dir_lba = struct.unpack_from("<I", record, 2)[0]
        dir_length = struct.unpack_from("<I", record, 10)[0]

        if dir_lba == 0 or dir_length == 0:
            return []

        # Leer todos los sectores del directorio
        sector_count = math.ceil(dir_length / SECTOR_SIZE)
        dir_data = self.read_sector(dir_lba, sector_count)

        entries: list[dict] = []
        offset = 0

        while offset < dir_length:
            # Longitud del registro actual
            rec_len = dir_data[offset]

            # Un registro de longitud 0 indica padding al final del sector
            if rec_len == 0:
                # Avanzar al inicio del siguiente sector
                next_sector_offset = ((offset // SECTOR_SIZE) + 1) * SECTOR_SIZE
                if next_sector_offset >= dir_length:
                    break
                offset = next_sector_offset
                continue

            # Verificar que hay suficientes datos para parsear
            if offset + rec_len > len(dir_data):
                break

            entry_raw = dir_data[offset : offset + rec_len]

            # Parsear campos de la entrada
            extent_lba = struct.unpack_from("<I", entry_raw, 2)[0]
            data_length = struct.unpack_from("<I", entry_raw, 10)[0]
            file_flags = entry_raw[25]
            is_directory = bool(file_flags & DIR_FLAG_DIRECTORY)

            # Nombre del archivo
            name_length = entry_raw[32]
            if name_length > 0 and 33 + name_length <= len(entry_raw):
                raw_name = entry_raw[33 : 33 + name_length]
            else:
                raw_name = b""

            name = _decode_directory_name(raw_name)

            # Omitir entradas especiales '.' y '..' (bytes 0x00 y 0x01)
            if raw_name == b"\x00" or raw_name == b"\x01":
                offset += rec_len
                continue

            entries.append(
                {
                    "name": name,
                    "extent_lba": extent_lba,
                    "data_length": data_length,
                    "is_directory": is_directory,
                    "raw": entry_raw,
                }
            )

            offset += rec_len

        return entries

    # -------------------------------------------------------------------------
    # Búsqueda y lectura de archivos
    # -------------------------------------------------------------------------

    def find_file(self, path: str) -> dict | None:
        """Busca un archivo por ruta dentro de la imagen ISO.

        La búsqueda es case-insensitive y acepta separadores ``/`` o ``\\``.
        No es necesario incluir la versión de archivo (``";1"``).

        Args:
            path: Ruta relativa al archivo (e.g. ``"SYSTEM.CNF"`` o
                  ``"SUBDIR/FILE.DAT"``).

        Returns:
            Diccionario con la información del archivo si se encuentra,
            o ``None`` si no existe.
        """
        # Normalizar la ruta: separar componentes, convertir a mayúsculas
        path = path.replace("\\", "/").strip("/")
        parts = [p.upper() for p in path.split("/") if p]

        if not parts:
            return None

        pvd = self.get_primary_volume_descriptor()
        current_record = pvd["root_dir_record"]

        # Recorrer cada componente de la ruta
        for i, part in enumerate(parts):
            entries = self.read_directory(current_record)
            is_last = i == len(parts) - 1

            found = False
            for entry in entries:
                entry_name = entry["name"].upper()
                if entry_name == part:
                    if is_last:
                        return entry
                    if entry["is_directory"]:
                        current_record = entry["raw"]
                        found = True
                        break
                    else:
                        # Se esperaba un directorio intermedio pero es un archivo
                        return None

            if not found and not is_last:
                return None

        return None

    def read_file(self, path: str) -> bytes:
        """Lee el contenido completo de un archivo dentro de la imagen ISO.

        Args:
            path: Ruta relativa al archivo (e.g. ``"SYSTEM.CNF"``).

        Returns:
            Contenido del archivo como bytes.

        Raises:
            FileNotFoundError: Si el archivo no se encuentra en la ISO.
        """
        entry = self.find_file(path)
        if entry is None:
            raise FileNotFoundError(
                f"Archivo no encontrado en la ISO: {path!r}"
            )

        extent_lba = entry["extent_lba"]
        data_length = entry["data_length"]

        if data_length == 0:
            return b""

        sector_count = math.ceil(data_length / SECTOR_SIZE)
        raw_data = self.read_sector(extent_lba, sector_count)

        # Retornar solo la cantidad exacta de bytes del archivo
        return raw_data[:data_length]

    def list_root(self) -> list[str]:
        """Lista los nombres de las entradas en el directorio raíz.

        Returns:
            Lista de nombres de archivos y directorios en la raíz de la ISO.
        """
        pvd = self.get_primary_volume_descriptor()
        entries = self.read_directory(pvd["root_dir_record"])
        return [entry["name"] for entry in entries]


# =============================================================================
# Funciones auxiliares internas
# =============================================================================


def _decode_directory_name(raw_name: bytes) -> str:
    """Decodifica el nombre de un archivo/directorio ISO9660.

    Elimina el sufijo de versión (``;1``) y maneja los identificadores
    especiales ``.`` y ``..``.

    Args:
        raw_name: Nombre crudo del registro de directorio.

    Returns:
        Nombre limpio como cadena de texto.
    """
    if raw_name == b"\x00":
        return "."
    if raw_name == b"\x01":
        return ".."

    name = raw_name.decode("ascii", errors="replace")

    # Eliminar versión del archivo (e.g. ";1")
    if ";" in name:
        name = name.split(";")[0]

    # Eliminar punto final residual (ISO9660 Level 1 agrega '.' al final)
    if name.endswith("."):
        name = name[:-1]

    return name


def _extract_game_id_from_system_cnf(data: bytes) -> str | None:
    """Extrae el Game ID del contenido de SYSTEM.CNF de PS2.

    Busca la línea ``BOOT2 = cdrom0:\\XXXX_XXX.XX;1`` y extrae el
    identificador del juego (e.g. ``"SLUS_200.01"``).

    Args:
        data: Contenido crudo del archivo SYSTEM.CNF.

    Returns:
        Game ID como cadena, o ``None`` si no se pudo extraer.
    """
    try:
        text = data.decode("ascii", errors="replace")
    except Exception:
        return None

    match = _GAME_ID_PATTERN.search(text)
    if match:
        return match.group(1)

    return None


def _detect_bin_cue(iso_path: str) -> bool:
    """Detecta si la ruta apunta a un archivo BIN o CUE en lugar de ISO.

    Args:
        iso_path: Ruta al archivo a verificar.

    Returns:
        ``True`` si la extensión es ``.bin`` o ``.cue``.
    """
    ext = os.path.splitext(iso_path)[1].lower()
    return ext in BIN_CUE_EXTENSIONS


# =============================================================================
# Funciones públicas de validación e información
# =============================================================================


def validate_ps2_iso(iso_path: str) -> dict:
    """Valida que un archivo ISO sea una imagen de disco PS2 válida.

    Realiza las siguientes verificaciones:
    1. El archivo existe y es legible.
    2. Tiene un tamaño razonable.
    3. Contiene un PVD ISO9660 válido.
    4. Contiene el archivo ``SYSTEM.CNF`` (requerido para PS2).
    5. Extrae el Game ID del ``SYSTEM.CNF``.

    Args:
        iso_path: Ruta al archivo de imagen ISO.

    Returns:
        Diccionario con:
            - ``valid`` (bool): ``True`` si es una ISO PS2 válida.
            - ``game_id`` (str | None): Identificador del juego (e.g. ``"SLUS_200.01"``).
            - ``title`` (str | None): Volume ID de la ISO (usado como título).
            - ``errors`` (list[str]): Lista de errores encontrados.
            - ``file_size`` (int): Tamaño del archivo en bytes (0 si no existe).
            - ``disc_type`` (str): ``"CD"`` si < 700 MB, ``"DVD"`` en caso contrario.
    """
    errors: list[str] = []
    game_id: str | None = None
    title: str | None = None
    file_size: int = 0
    disc_type: str = "DVD"

    # --- Detección de formato BIN/CUE ---
    if _detect_bin_cue(iso_path):
        errors.append(
            f"El archivo parece ser formato BIN/CUE ({os.path.splitext(iso_path)[1]}). "
            "Este conversor requiere una imagen ISO9660 (.iso). "
            "Convierta el archivo a ISO primero."
        )
        return {
            "valid": False,
            "game_id": None,
            "title": None,
            "errors": errors,
            "file_size": 0,
            "disc_type": "DVD",
        }

    # --- Verificar existencia y permisos ---
    if not os.path.exists(iso_path):
        errors.append(f"El archivo no existe: {iso_path}")
        return {
            "valid": False,
            "game_id": None,
            "title": None,
            "errors": errors,
            "file_size": 0,
            "disc_type": "DVD",
        }

    if not os.path.isfile(iso_path):
        errors.append(f"La ruta no es un archivo regular: {iso_path}")
        return {
            "valid": False,
            "game_id": None,
            "title": None,
            "errors": errors,
            "file_size": 0,
            "disc_type": "DVD",
        }

    try:
        file_size = os.path.getsize(iso_path)
    except OSError as e:
        errors.append(f"No se pudo obtener el tamaño del archivo: {e}")
        return {
            "valid": False,
            "game_id": None,
            "title": None,
            "errors": errors,
            "file_size": 0,
            "disc_type": "DVD",
        }

    # --- Determinar tipo de disco ---
    disc_type = "CD" if file_size < CD_SIZE_THRESHOLD else "DVD"

    # --- Verificar tamaño mínimo ---
    if file_size < MIN_ISO_SIZE:
        errors.append(
            f"El archivo es demasiado pequeño ({file_size} bytes). "
            f"Tamaño mínimo esperado: {MIN_ISO_SIZE} bytes."
        )
        return {
            "valid": False,
            "game_id": None,
            "title": None,
            "errors": errors,
            "file_size": file_size,
            "disc_type": disc_type,
        }

    # --- Abrir y validar ISO ---
    try:
        with ISO9660Reader(iso_path) as iso:
            # Verificar PVD
            try:
                pvd = iso.get_primary_volume_descriptor()
                title = pvd.get("volume_id") or None
            except ValueError as e:
                errors.append(f"PVD inválido: {e}")
                return {
                    "valid": False,
                    "game_id": None,
                    "title": None,
                    "errors": errors,
                    "file_size": file_size,
                    "disc_type": disc_type,
                }
            except IOError as e:
                errors.append(f"Error de lectura al acceder al PVD: {e}")
                return {
                    "valid": False,
                    "game_id": None,
                    "title": None,
                    "errors": errors,
                    "file_size": file_size,
                    "disc_type": disc_type,
                }

            # Verificar presencia de SYSTEM.CNF
            try:
                system_cnf_entry = iso.find_file("SYSTEM.CNF")
            except (IOError, ValueError) as e:
                errors.append(f"Error al buscar SYSTEM.CNF: {e}")
                return {
                    "valid": False,
                    "game_id": None,
                    "title": title,
                    "errors": errors,
                    "file_size": file_size,
                    "disc_type": disc_type,
                }

            if system_cnf_entry is None:
                errors.append(
                    "No se encontró SYSTEM.CNF en el directorio raíz. "
                    "Este archivo es requerido para discos PS2."
                )
                return {
                    "valid": False,
                    "game_id": None,
                    "title": title,
                    "errors": errors,
                    "file_size": file_size,
                    "disc_type": disc_type,
                }

            # Extraer Game ID del SYSTEM.CNF
            try:
                cnf_data = iso.read_file("SYSTEM.CNF")
                game_id = _extract_game_id_from_system_cnf(cnf_data)
                if game_id is None:
                    errors.append(
                        "No se pudo extraer el Game ID del SYSTEM.CNF. "
                        "El formato BOOT2 no fue reconocido."
                    )
            except (IOError, ValueError) as e:
                errors.append(f"Error al leer SYSTEM.CNF: {e}")

    except (FileNotFoundError, PermissionError, ValueError) as e:
        errors.append(f"No se pudo abrir la ISO: {e}")
        return {
            "valid": False,
            "game_id": None,
            "title": None,
            "errors": errors,
            "file_size": file_size,
            "disc_type": disc_type,
        }
    except Exception as e:
        errors.append(f"Error inesperado al procesar la ISO: {e}")
        return {
            "valid": False,
            "game_id": None,
            "title": None,
            "errors": errors,
            "file_size": file_size,
            "disc_type": disc_type,
        }

    # Si no hay errores críticos (solo warnings como game_id faltante),
    # se considera válida si SYSTEM.CNF existe
    is_valid = not any(
        "No se encontró SYSTEM.CNF" in err or "PVD inválido" in err
        for err in errors
    )

    return {
        "valid": is_valid,
        "game_id": game_id,
        "title": title,
        "errors": errors,
        "file_size": file_size,
        "disc_type": disc_type,
    }


def get_iso_info(iso_path: str) -> dict:
    """Obtiene información detallada de una imagen ISO9660.

    Args:
        iso_path: Ruta al archivo de imagen ISO.

    Returns:
        Diccionario con:
            - ``file_size`` (int): Tamaño del archivo en bytes.
            - ``game_id`` (str | None): Game ID si es un disco PS2.
            - ``disc_type`` (str): ``"CD"`` o ``"DVD"``.
            - ``volume_id`` (str): Volume ID de la ISO.
            - ``system_id`` (str): System ID de la ISO.
            - ``root_files`` (list[str]): Lista de archivos en el directorio raíz.

    Raises:
        FileNotFoundError: Si el archivo no existe.
        ValueError: Si el archivo no es una ISO9660 válida.
    """
    file_size = os.path.getsize(iso_path)
    disc_type = "CD" if file_size < CD_SIZE_THRESHOLD else "DVD"
    game_id: str | None = None

    with ISO9660Reader(iso_path) as iso:
        pvd = iso.get_primary_volume_descriptor()
        root_files = iso.list_root()

        # Intentar extraer Game ID si hay SYSTEM.CNF
        try:
            cnf_data = iso.read_file("SYSTEM.CNF")
            game_id = _extract_game_id_from_system_cnf(cnf_data)
        except FileNotFoundError:
            pass
        except (IOError, ValueError):
            pass

    return {
        "file_size": file_size,
        "game_id": game_id,
        "disc_type": disc_type,
        "volume_id": pvd["volume_id"],
        "system_id": pvd["system_id"],
        "root_files": root_files,
    }
