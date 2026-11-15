"""
pkg_builder.py - Módulo principal de ensamblaje de PKG para el conversor PS2-a-PS4.

Orquesta todos los módulos auxiliares (sfo_builder, gp4_builder, config_generator,
iso_utils) para construir la estructura de directorios completa de un proyecto
PS2 Classics empaquetable como PKG de PS4.

Modos de operación:
    1. Modo directorio: genera la estructura en disco lista para ser procesada
       por orbis-pub-cmd externamente.
    2. Modo autónomo: si orbis-pub-cmd.exe está disponible en PATH o en el
       directorio de la herramienta, lo invoca automáticamente para generar
       el PKG final.

Ejemplo de uso rápido::

    from src.pkg_builder import quick_convert

    project_path = quick_convert(
        iso_path="mi_juego.iso",
        output_dir="output",
        eboot_path="eboot.bin",
        title="Mi Juego PS2",
    )
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import shutil
import struct
import subprocess
import zlib
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# ── Importaciones de módulos hermanos ────────────────────────────────────────
# Estos módulos pueden no existir todavía; se importan de forma defensiva
# para que el módulo sea funcional incluso durante desarrollo incremental.

try:
    from .sfo_builder import SFOBuilder
except ImportError:
    try:
        from sfo_builder import SFOBuilder  # type: ignore[no-redef]
    except ImportError:
        SFOBuilder = None  # type: ignore[assignment,misc]

try:
    from .gp4_builder import GP4Builder, create_ps2_classic_gp4
except ImportError:
    try:
        from gp4_builder import GP4Builder, create_ps2_classic_gp4  # type: ignore[no-redef]
    except ImportError:
        GP4Builder = None  # type: ignore[assignment,misc]
        create_ps2_classic_gp4 = None  # type: ignore[assignment,misc]

try:
    from .config_generator import EmulatorConfig, get_game_config, detect_game_id
except ImportError:
    try:
        from config_generator import EmulatorConfig, get_game_config, detect_game_id  # type: ignore[no-redef]
    except ImportError:
        EmulatorConfig = None  # type: ignore[assignment,misc]
        get_game_config = None  # type: ignore[assignment,misc]
        detect_game_id = None  # type: ignore[assignment,misc]

try:
    from .iso_utils import validate_ps2_iso, get_iso_info
except ImportError:
    try:
        from iso_utils import validate_ps2_iso, get_iso_info  # type: ignore[no-redef]
    except ImportError:
        validate_ps2_iso = None  # type: ignore[assignment,misc]
        get_iso_info = None  # type: ignore[assignment,misc]


# ── Logger del módulo ────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)


# ── Constantes ───────────────────────────────────────────────────────────────

# Rango de CUSA IDs para generación automática (rango alto para evitar colisiones
# con títulos oficiales de Sony)
_CUSA_RANGE_MIN = 90000
_CUSA_RANGE_MAX = 99999

# Tamaño del icono placeholder en píxeles
_ICON_SIZE = 512

# Color de fondo del placeholder (azul oscuro PS2)
_PLACEHOLDER_BG_COLOR = (0x1A, 0x23, 0x7E)

# Color del texto en el placeholder
_PLACEHOLDER_TEXT_COLOR = (0xFF, 0xFF, 0xFF)


# ══════════════════════════════════════════════════════════════════════════════
# Generador de PNG placeholder (Python puro, sin dependencias externas)
# ══════════════════════════════════════════════════════════════════════════════

def _create_placeholder_icon_pure(
    output_path: str,
    title: str,
    width: int = _ICON_SIZE,
    height: int = _ICON_SIZE,
    bg_color: tuple = _PLACEHOLDER_BG_COLOR,
    text_color: tuple = _PLACEHOLDER_TEXT_COLOR,
) -> None:
    """Genera un PNG placeholder de color sólido en Python puro.

    Crea un archivo PNG válido de ``width x height`` con el color de fondo
    indicado. No incluye renderizado de texto (para eso se necesita Pillow).

    El formato PNG se construye manualmente:
        - Signature (8 bytes)
        - Chunk IHDR (13 bytes de datos)
        - Chunk IDAT (datos de imagen comprimidos con zlib)
        - Chunk IEND (0 bytes de datos)

    Args:
        output_path: Ruta del archivo PNG de salida.
        title: Título del juego (no usado en modo puro, reservado para
               compatibilidad con la versión Pillow).
        width: Ancho de la imagen en píxeles.
        height: Alto de la imagen en píxeles.
        bg_color: Tupla RGB (0-255) del color de fondo.
        text_color: Tupla RGB (0-255) del color de texto (no usado en modo puro).
    """
    def _make_chunk(chunk_type: bytes, data: bytes) -> bytes:
        """Construye un chunk PNG: length(4) + type(4) + data + crc(4)."""
        chunk_body = chunk_type + data
        return (
            struct.pack(">I", len(data))
            + chunk_body
            + struct.pack(">I", zlib.crc32(chunk_body) & 0xFFFFFFFF)
        )

    # Firma PNG
    signature = b"\x89PNG\r\n\x1a\n"

    # IHDR: width, height, bit_depth=8, color_type=2(RGB),
    # compression=0, filter=0, interlace=0
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_chunk = _make_chunk(b"IHDR", ihdr_data)

    # Datos de imagen: cada fila tiene filter_byte(0) + width*3 bytes RGB
    r, g, b = bg_color
    row = b"\x00" + bytes([r, g, b]) * width
    raw_data = row * height

    # Comprimir con zlib
    compressed = zlib.compress(raw_data)
    idat_chunk = _make_chunk(b"IDAT", compressed)

    # IEND
    iend_chunk = _make_chunk(b"IEND", b"")

    # Escribir el archivo completo
    with open(output_path, "wb") as f:
        f.write(signature + ihdr_chunk + idat_chunk + iend_chunk)


def _create_placeholder_icon_pillow(
    output_path: str,
    title: str,
    width: int = _ICON_SIZE,
    height: int = _ICON_SIZE,
    bg_color: tuple = _PLACEHOLDER_BG_COLOR,
    text_color: tuple = _PLACEHOLDER_TEXT_COLOR,
) -> None:
    """Genera un PNG placeholder con texto renderizado usando Pillow.

    Crea una imagen de ``width x height`` con el color de fondo indicado
    y el título del juego centrado en texto blanco.

    Args:
        output_path: Ruta del archivo PNG de salida.
        title: Título del juego a renderizar en la imagen.
        width: Ancho de la imagen en píxeles.
        height: Alto de la imagen en píxeles.
        bg_color: Tupla RGB (0-255) del color de fondo.
        text_color: Tupla RGB (0-255) del color del texto.
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # Intentar cargar una fuente de tamaño razonable; si falla usar la default
    font_size = 36
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", font_size)
        except (OSError, IOError):
            font = ImageFont.load_default()

    # Dividir el título en líneas si es muy largo (máx ~20 chars por línea)
    max_chars_per_line = 20
    words = title.split()
    lines: list[str] = []
    current_line = ""

    for word in words:
        test_line = f"{current_line} {word}".strip() if current_line else word
        if len(test_line) <= max_chars_per_line:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    if not lines:
        lines = ["PS2 Classic"]

    # Calcular posición vertical centrada
    line_height = font_size + 8
    total_text_height = len(lines) * line_height
    y_start = (height - total_text_height) // 2

    # Etiqueta "PS2" arriba del título
    ps2_label = "── PS2 Classic ──"
    try:
        ps2_bbox = draw.textbbox((0, 0), ps2_label, font=font)
        ps2_w = ps2_bbox[2] - ps2_bbox[0]
    except AttributeError:
        # Pillow antiguo sin textbbox
        ps2_w = len(ps2_label) * (font_size // 2)

    draw.text(
        ((width - ps2_w) // 2, y_start - line_height - 20),
        ps2_label,
        fill=(0x80, 0x80, 0xFF),
        font=font,
    )

    # Renderizar cada línea del título
    for i, line in enumerate(lines):
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
        except AttributeError:
            text_w = len(line) * (font_size // 2)

        x = (width - text_w) // 2
        y = y_start + i * line_height
        draw.text((x, y), line, fill=text_color, font=font)

    img.save(output_path, "PNG")


def create_placeholder_icon(output_path: str, title: str) -> None:
    """Genera un icono placeholder para el proyecto PKG.

    Intenta usar Pillow para un resultado con texto renderizado.
    Si Pillow no está disponible, genera un PNG de color sólido
    usando un generador en Python puro.

    Args:
        output_path: Ruta del archivo icon0.png de salida.
        title: Título del juego para mostrar en el icono.
    """
    try:
        _create_placeholder_icon_pillow(output_path, title)
        logger.info("Icono placeholder generado con Pillow: %s", output_path)
    except ImportError:
        logger.info(
            "Pillow no disponible, generando icono de color sólido sin texto"
        )
        _create_placeholder_icon_pure(output_path, title)
        logger.info("Icono placeholder (puro) generado: %s", output_path)


# ══════════════════════════════════════════════════════════════════════════════
# Clase principal: PKGProject
# ══════════════════════════════════════════════════════════════════════════════

class PKGProject:
    """Proyecto de ensamblaje de PKG para PS2 Classics en PS4.

    Orquesta la creación de la estructura de directorios completa con todos
    los archivos necesarios (PARAM.SFO, icon0.png, ISOs, config, eboot.bin)
    y opcionalmente genera el PKG final con orbis-pub-cmd.

    Attributes:
        project_name: Nombre identificador del proyecto (usado para
                      el directorio de salida).
        output_dir: Directorio base donde se crea el proyecto.
        title: Título del juego que se muestra en la XMB del PS4.
        title_id: Identificador CUSA del título (e.g. ``"CUSA90001"``).
        content_id: Content ID completo del paquete PS4.
        ps2_game_id: Serial original del juego PS2 (e.g. ``"SLUS-20001"``).
        iso_paths: Lista de rutas a los archivos ISO de PS2 (multi-disco).
        icon_path: Ruta a un icon0.png personalizado (512x512).
        bg_path: Ruta a un pic0.png de fondo personalizado.
        startup_image_path: Ruta a una imagen de inicio personalizada.
        eboot_path: Ruta al eboot.bin del emulador PS2.
        emulator_config: Configuración del emulador (del módulo config_generator).

    Ejemplo::

        project = PKGProject("mi_juego", "output")
        project.title = "Shadow of the Colossus"
        project.iso_paths = ["shadow_colossus.iso"]
        project.eboot_path = "eboot.bin"
        project.auto_detect()
        errors = project.validate()
        if not errors:
            project_path = project.build_project()
    """

    def __init__(
        self,
        project_name: Optional[str] = None,
        output_dir: Optional[str] = None,
        iso_paths: Optional[list[str]] = None,
        eboot_path: Optional[str] = None,
        game_id: Optional[str] = None,
        game_title: Optional[str] = None,
        title_id: Optional[str] = None,
        content_id: Optional[str] = None,
        emu_config: Optional[object] = None,
        game_config: Optional[dict] = None,
        icon_path: Optional[str] = None,
        pic_path: Optional[str] = None,
        progress_callback: Optional[object] = None,
        **kwargs,
    ) -> None:
        """Inicializa un nuevo proyecto PKG.

        Acepta tanto la inicialización posicional clásica (project_name, output_dir)
        como la inicialización por palabras clave desde la interfaz gráfica.
        """
        # Resolver nombre de proyecto y directorio de salida
        resolved_name = project_name or game_title or (
            os.path.splitext(os.path.basename(iso_paths[0]))[0] if iso_paths else "PS2_Game"
        )
        # Limpiar nombre para que sea un directorio válido en Windows
        clean_name = "".join(c for c in resolved_name if c.isalnum() or c in (" ", "_", "-")).strip()
        self._project_name: str = clean_name or "PS2_Game"
        self._output_dir: str = output_dir or os.path.abspath("output")

        # Propiedades del juego
        self.title: str = game_title or ""
        self.title_id: str = title_id or ""
        self.content_id: str = content_id or ""
        self.ps2_game_id: str = game_id or ""

        # Archivos de entrada
        self.iso_paths: list[str] = list(iso_paths) if iso_paths else []
        self.icon_path: Optional[str] = icon_path
        self.bg_path: Optional[str] = pic_path or kwargs.get("bg_path")
        self.startup_image_path: Optional[str] = kwargs.get("startup_image_path")
        self.eboot_path: Optional[str] = eboot_path

        # Configuración del emulador
        self.emulator_config: object | None = emu_config

        # Callback de progreso
        self.progress_callback = progress_callback

        logger.debug(
            "PKGProject creado: name='%s', output='%s'",
            self._project_name,
            self._output_dir,
        )

    # ── Propiedades ──────────────────────────────────────────────────────────

    @property
    def project_dir(self) -> str:
        """Ruta al directorio de construcción del proyecto.

        Returns:
            Ruta absoluta al subdirectorio del proyecto dentro de output_dir.
        """
        return os.path.abspath(
            os.path.join(self._output_dir, self._project_name)
        )

    # ── Generación de identificadores ────────────────────────────────────────

    def generate_title_id(self) -> str:
        """Genera un CUSA ID único para el proyecto.

        Genera un identificador en formato ``CUSAxxxxx`` donde los 5 dígitos
        están en el rango alto (90000-99999) para minimizar colisiones con
        títulos oficiales de Sony.

        Si ``ps2_game_id`` está definido, se usa como semilla para generar
        un ID determinista. En caso contrario, se genera uno aleatorio.

        Returns:
            String con el CUSA ID generado (e.g. ``"CUSA90123"``).
        """
        if self.ps2_game_id:
            # Generación determinista basada en el ID del juego PS2
            hash_digest = hashlib.md5(
                self.ps2_game_id.encode("utf-8")
            ).hexdigest()
            hash_int = int(hash_digest[:8], 16)
            cusa_num = _CUSA_RANGE_MIN + (hash_int % (_CUSA_RANGE_MAX - _CUSA_RANGE_MIN + 1))
        else:
            cusa_num = random.randint(_CUSA_RANGE_MIN, _CUSA_RANGE_MAX)

        title_id = f"CUSA{cusa_num:05d}"
        logger.info("Title ID generado: %s", title_id)
        return title_id

    def generate_content_id(self) -> str:
        """Genera un Content ID válido para PS4 a partir del title_id.

        Formato: ``UP9000-{title_id}_00-{game_id_cleaned}0001``

        El ``game_id_cleaned`` se obtiene eliminando guiones del
        ``ps2_game_id`` y truncando/rellenando a 12 caracteres.
        Si no hay ``ps2_game_id``, se usan ceros.

        Returns:
            String con el content ID de 36 caracteres.

        Raises:
            ValueError: Si ``title_id`` no está definido.
        """
        if not self.title_id:
            raise ValueError(
                "title_id debe estar definido antes de generar el content_id. "
                "Llame a generate_title_id() primero."
            )

        # Limpiar el game_id: quitar guiones y caracteres no alfanuméricos
        if self.ps2_game_id:
            cleaned = "".join(
                c for c in self.ps2_game_id.upper() if c.isalnum()
            )
        else:
            cleaned = ""

        # Rellenar con ceros hasta 12 caracteres y agregar "0001"
        game_part = cleaned[:12].ljust(12, "0") + "0001"
        # El game_part debe tener exactamente 16 caracteres
        game_part = game_part[:16]

        content_id = f"UP9000-{self.title_id}_00-{game_part}"

        # Validar longitud (debe ser exactamente 36 caracteres)
        if len(content_id) != 36:
            logger.warning(
                "Content ID generado tiene longitud %d (esperada 36): '%s'",
                len(content_id),
                content_id,
            )
            # Ajustar si es necesario: truncar o rellenar game_part
            expected_game_len = 36 - len(f"UP9000-{self.title_id}_00-")
            game_part = game_part[:expected_game_len].ljust(
                expected_game_len, "0"
            )
            content_id = f"UP9000-{self.title_id}_00-{game_part}"

        logger.info("Content ID generado: %s", content_id)
        return content_id

    # ── Auto-detección ───────────────────────────────────────────────────────

    def auto_detect(self) -> None:
        """Auto-detecta la información del juego desde la primera ISO.

        Utiliza ``iso_utils.get_iso_info`` para extraer el título y el
        serial del juego, y ``config_generator.detect_game_id`` para
        obtener la configuración del emulador si está disponible.

        Si los módulos auxiliares no están disponibles, se emiten
        advertencias y se asignan valores por defecto.

        Raises:
            ValueError: Si ``iso_paths`` está vacío.
        """
        if not self.iso_paths:
            raise ValueError(
                "No se han proporcionado rutas de ISO. "
                "Asigne iso_paths antes de llamar a auto_detect()."
            )

        first_iso = self.iso_paths[0]
        logger.info("Auto-detectando información desde: %s", first_iso)

        # ── Detección del ID del juego PS2 ───────────────────────────────
        if detect_game_id is not None:
            try:
                detected_id = detect_game_id(first_iso)
                if detected_id:
                    self.ps2_game_id = detected_id
                    logger.info("Game ID PS2 detectado: %s", detected_id)
            except Exception as e:
                logger.warning("Error detectando game ID: %s", e)
        else:
            logger.warning(
                "Módulo config_generator no disponible. "
                "No se pudo detectar el game ID."
            )

        # ── Detección de información de la ISO ───────────────────────────
        if get_iso_info is not None:
            try:
                iso_info = get_iso_info(first_iso)
                if iso_info:
                    if not self.title and iso_info.get("title"):
                        self.title = iso_info["title"]
                        logger.info("Título detectado: %s", self.title)
                    if not self.ps2_game_id and iso_info.get("game_id"):
                        self.ps2_game_id = iso_info["game_id"]
                        logger.info(
                            "Game ID detectado desde ISO info: %s",
                            self.ps2_game_id,
                        )
            except Exception as e:
                logger.warning("Error obteniendo info de ISO: %s", e)
        else:
            logger.warning(
                "Módulo iso_utils no disponible. "
                "No se pudo obtener información de la ISO."
            )

        # ── Configuración del emulador ───────────────────────────────────
        if get_game_config is not None and self.ps2_game_id:
            try:
                config = get_game_config(self.ps2_game_id)
                if config:
                    self.emulator_config = config
                    logger.info(
                        "Configuración del emulador cargada para: %s",
                        self.ps2_game_id,
                    )
            except Exception as e:
                logger.warning(
                    "Error obteniendo config del emulador: %s", e
                )

        # ── Asignar valores por defecto si aún no hay datos ──────────────
        if not self.title:
            # Usar el nombre del archivo ISO como título de respaldo
            iso_basename = os.path.splitext(os.path.basename(first_iso))[0]
            self.title = iso_basename.replace("_", " ").replace(".", " ").strip()
            logger.info("Título asignado desde nombre de archivo: %s", self.title)

        if not self.title_id:
            self.title_id = self.generate_title_id()

        if not self.content_id:
            self.content_id = self.generate_content_id()

    # ── Validación ───────────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Valida todas las configuraciones del proyecto.

        Comprueba que todos los campos obligatorios estén definidos y
        que los archivos referenciados existan en disco.

        Returns:
            Lista de mensajes de error. Si está vacía, el proyecto es válido.
        """
        errors: list[str] = []

        # ── Campos obligatorios ──────────────────────────────────────────
        if not self.title:
            errors.append("El título del juego (title) es obligatorio.")

        if not self.title_id:
            errors.append("El title_id (CUSA ID) es obligatorio.")
        elif not self.title_id.startswith("CUSA") or len(self.title_id) != 9:
            errors.append(
                f"title_id '{self.title_id}' tiene formato inválido. "
                "Se espera 'CUSAxxxxx' (9 caracteres)."
            )

        if not self.content_id:
            errors.append("El content_id es obligatorio.")
        elif len(self.content_id) != 36:
            errors.append(
                f"content_id '{self.content_id}' debe tener exactamente "
                f"36 caracteres (tiene {len(self.content_id)})."
            )

        # ── Archivos ISO ─────────────────────────────────────────────────
        if not self.iso_paths:
            errors.append(
                "Se requiere al menos una ruta de ISO en iso_paths."
            )
        else:
            for i, iso_path in enumerate(self.iso_paths):
                if not os.path.isfile(iso_path):
                    errors.append(
                        f"Archivo ISO #{i + 1} no encontrado: '{iso_path}'"
                    )
                elif validate_ps2_iso is not None:
                    try:
                        is_valid = validate_ps2_iso(iso_path)
                        if not is_valid:
                            errors.append(
                                f"ISO #{i + 1} no es una ISO de PS2 válida: "
                                f"'{iso_path}'"
                            )
                    except Exception as e:
                        logger.warning(
                            "Error validando ISO #%d: %s", i + 1, e
                        )

        # ── Archivos opcionales ──────────────────────────────────────────
        if self.icon_path and not os.path.isfile(self.icon_path):
            errors.append(
                f"Icono personalizado no encontrado: '{self.icon_path}'"
            )

        if self.bg_path and not os.path.isfile(self.bg_path):
            errors.append(
                f"Imagen de fondo (pic0.png) no encontrada: '{self.bg_path}'"
            )

        if self.startup_image_path and not os.path.isfile(self.startup_image_path):
            errors.append(
                f"Imagen de inicio no encontrada: '{self.startup_image_path}'"
            )

        if self.eboot_path and not os.path.isfile(self.eboot_path):
            errors.append(
                f"eboot.bin no encontrado: '{self.eboot_path}'"
            )

        if errors:
            for err in errors:
                logger.error("Validación fallida: %s", err)
        else:
            logger.info("Validación completada sin errores.")

        return errors

    # ── Construcción del proyecto ─────────────────────────────────────────────

    def build_project(self) -> str:
        """Crea la estructura de directorios completa del proyecto PKG.

        Genera todos los archivos necesarios en el directorio del proyecto:
            - ``sce_sys/param.sfo`` (usando SFOBuilder)
            - ``sce_sys/icon0.png`` (copia personalizado o genera placeholder)
            - ``sce_sys/pic0.png`` (si se proporcionó)
            - ``image/disc01.iso``, ``image/disc02.iso``, etc. (copia/enlaza ISOs)
            - ``config-emu-ps4.txt`` (configuración del emulador)
            - ``eboot.bin`` (copia del binario del emulador)
            - Archivo ``.gp4`` (usando GP4Builder)

        Returns:
            Ruta absoluta al directorio del proyecto creado.

        Raises:
            ValueError: Si la validación del proyecto falla.
            OSError: Si hay errores de escritura en disco.
        """
        errors = self.validate()
        if errors:
            error_msg = "El proyecto tiene errores de validación:\n" + "\n".join(
                f"  - {e}" for e in errors
            )
            raise ValueError(error_msg)

        proj_dir = self.project_dir
        sce_sys_dir = os.path.join(proj_dir, "sce_sys")
        image_dir = os.path.join(proj_dir, "image")

        logger.info("Construyendo proyecto en: %s", proj_dir)

        # ── Crear estructura de directorios ──────────────────────────────
        os.makedirs(sce_sys_dir, exist_ok=True)
        os.makedirs(image_dir, exist_ok=True)
        logger.debug("Directorios creados: sce_sys, image")

        # ── 1. PARAM.SFO ─────────────────────────────────────────────────
        sfo_path = os.path.join(sce_sys_dir, "param.sfo")
        self._build_sfo(sfo_path)

        # ── 2. icon0.png ─────────────────────────────────────────────────
        icon_dest = os.path.join(sce_sys_dir, "icon0.png")
        self._build_icon(icon_dest)

        # ── 3. pic0.png (fondo, opcional) ────────────────────────────────
        if self.bg_path:
            pic0_dest = os.path.join(sce_sys_dir, "pic0.png")
            shutil.copy2(self.bg_path, pic0_dest)
            logger.info("pic0.png copiado: %s → %s", self.bg_path, pic0_dest)

        # ── 4. Imagen de inicio (opcional) ───────────────────────────────
        if self.startup_image_path:
            pic1_dest = os.path.join(sce_sys_dir, "pic1.png")
            shutil.copy2(self.startup_image_path, pic1_dest)
            logger.info(
                "pic1.png copiado: %s → %s",
                self.startup_image_path,
                pic1_dest,
            )

        # ── 5. ISOs de disco ─────────────────────────────────────────────
        self._build_disc_images(image_dir)

        # ── 6. Configuración del emulador ────────────────────────────────
        config_path = os.path.join(proj_dir, "config-emu-ps4.txt")
        self._build_emulator_config(config_path)

        # ── 7. eboot.bin ─────────────────────────────────────────────────
        eboot_dest = os.path.join(proj_dir, "eboot.bin")
        self._build_eboot(eboot_dest)

        # ── 8. Archivo GP4 ──────────────────────────────────────────────
        gp4_path = os.path.join(proj_dir, f"{self._project_name}.gp4")
        self._build_gp4(gp4_path, proj_dir)

        logger.info("Proyecto construido exitosamente: %s", proj_dir)
        return proj_dir

    # ── Sub-constructores privados ───────────────────────────────────────────

    def _build_sfo(self, sfo_path: str) -> None:
        """Genera el archivo PARAM.SFO del proyecto.

        Args:
            sfo_path: Ruta de salida del archivo SFO.
        """
        if SFOBuilder is None:
            logger.error(
                "SFOBuilder no disponible. No se pudo generar PARAM.SFO."
            )
            raise ImportError(
                "El módulo sfo_builder es necesario para generar PARAM.SFO. "
                "Asegúrese de que esté en el mismo paquete."
            )

        builder = SFOBuilder()
        builder.set_title(self.title)
        builder.set_title_id(self.title_id)
        builder.set_content_id(self.content_id)
        builder.save(sfo_path)
        logger.info("PARAM.SFO generado: %s", sfo_path)

    def _build_icon(self, icon_dest: str) -> None:
        """Copia el icono personalizado o genera un placeholder.

        Args:
            icon_dest: Ruta de destino para icon0.png.
        """
        if self.icon_path and os.path.isfile(self.icon_path):
            shutil.copy2(self.icon_path, icon_dest)
            logger.info(
                "icon0.png personalizado copiado: %s → %s",
                self.icon_path,
                icon_dest,
            )
        else:
            if self.icon_path:
                logger.warning(
                    "Icono personalizado no encontrado ('%s'), "
                    "generando placeholder.",
                    self.icon_path,
                )
            else:
                logger.info(
                    "No se proporcionó icono personalizado, "
                    "generando placeholder."
                )
            create_placeholder_icon(icon_dest, self.title)

    def _build_disc_images(self, image_dir: str) -> None:
        """Copia o enlaza los archivos ISO al directorio image/.

        Intenta crear enlaces simbólicos para ahorrar espacio en disco.
        Si falla (permisos en Windows), recurre a copiar el archivo.

        Args:
            image_dir: Directorio de destino para las imágenes de disco.
        """
        for idx, iso_path in enumerate(self.iso_paths, start=1):
            disc_name = f"disc{idx:02d}.iso"
            dest = os.path.join(image_dir, disc_name)
            iso_abs = os.path.abspath(iso_path)

            # Intentar enlace simbólico primero (ahorra espacio)
            try:
                if os.path.exists(dest):
                    os.remove(dest)
                os.symlink(iso_abs, dest)
                logger.info(
                    "ISO enlazada (symlink): %s → %s", iso_abs, dest
                )
            except (OSError, NotImplementedError):
                # En Windows sin privilegios de admin, symlink puede fallar
                logger.info(
                    "Symlink no disponible, copiando ISO: %s → %s",
                    iso_abs,
                    dest,
                )
                shutil.copy2(iso_abs, dest)
                logger.info("ISO copiada: %s → %s", iso_abs, dest)

    def _build_emulator_config(self, config_path: str) -> None:
        """Genera el archivo de configuración del emulador.

        Si se proporcionó un ``EmulatorConfig`` externo, se serializa.
        Si no, se genera una configuración mínima por defecto.

        Args:
            config_path: Ruta de salida para config-emu-ps4.txt.
        """
        if self.emulator_config is not None:
            # Si EmulatorConfig tiene método to_file o similar
            if hasattr(self.emulator_config, "to_file"):
                self.emulator_config.to_file(config_path)  # type: ignore[union-attr]
                logger.info(
                    "Configuración del emulador escrita: %s", config_path
                )
                return
            elif hasattr(self.emulator_config, "to_string"):
                config_text = self.emulator_config.to_string()  # type: ignore[union-attr]
                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(config_text)
                logger.info(
                    "Configuración del emulador escrita: %s", config_path
                )
                return

        # Configuración mínima por defecto
        default_config_lines = [
            "# PS2 Classics Emulator Configuration",
            f"# Game: {self.title}",
            f"# Game ID: {self.ps2_game_id}",
            f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "--icon-height=512",
            "--icon-width=512",
            "",
        ]

        # Agregar configuración de multi-disco si aplica
        if len(self.iso_paths) > 1:
            default_config_lines.append(
                f"--num-discs={len(self.iso_paths)}"
            )
            default_config_lines.append("")

        config_text = "\n".join(default_config_lines)

        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_text)

        logger.info(
            "Configuración del emulador por defecto escrita: %s",
            config_path,
        )

    def _build_eboot(self, eboot_dest: str) -> None:
        """Copia el eboot.bin del emulador PS2 al proyecto.

        Args:
            eboot_dest: Ruta de destino para eboot.bin.
        """
        if self.eboot_path and os.path.isfile(self.eboot_path):
            shutil.copy2(self.eboot_path, eboot_dest)
            logger.info(
                "eboot.bin copiado: %s → %s", self.eboot_path, eboot_dest
            )
        else:
            logger.warning(
                "eboot.bin no proporcionado o no encontrado ('%s'). "
                "El PKG no será funcional sin este archivo. "
                "Coloque un eboot.bin válido en: %s",
                self.eboot_path,
                eboot_dest,
            )

    def _build_gp4(self, gp4_path: str, proj_dir: str) -> None:
        """Genera el archivo de proyecto GP4 para orbis-pub-cmd.

        Args:
            gp4_path: Ruta de salida del archivo .gp4.
            proj_dir: Directorio raíz del proyecto.
        """
        if create_ps2_classic_gp4 is not None:
            try:
                create_ps2_classic_gp4(
                    content_id=self.content_id,
                    project_dir=proj_dir,
                    iso_paths=[
                        os.path.join(
                            proj_dir, "image", f"disc{i:02d}.iso"
                        )
                        for i in range(1, len(self.iso_paths) + 1)
                    ],
                    output_path=gp4_path,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                logger.info("Archivo GP4 generado: %s", gp4_path)
                return
            except Exception as e:
                logger.warning(
                    "Error generando GP4 con create_ps2_classic_gp4: %s. "
                    "Intentando con GP4Builder directamente.",
                    e,
                )

        # Fallback: construir manualmente con GP4Builder
        if GP4Builder is not None:
            builder = GP4Builder(self.content_id)
            builder.set_volume_timestamp(
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

            # Agregar todos los archivos del proyecto
            for dirpath, _dirnames, filenames in os.walk(proj_dir):
                for fname in filenames:
                    if fname.endswith(".gp4"):
                        continue  # No incluir el propio GP4
                    full_path = os.path.join(dirpath, fname)
                    rel_path = os.path.relpath(
                        full_path, proj_dir
                    ).replace("\\", "/")
                    builder.add_file(full_path, rel_path)

            builder.save(gp4_path)
            logger.info("Archivo GP4 generado (fallback): %s", gp4_path)
        else:
            logger.error(
                "GP4Builder no disponible. "
                "No se pudo generar el archivo de proyecto GP4."
            )

    # ── Construcción del PKG final ───────────────────────────────────────────

    def build_pkg(
        self, orbis_pub_cmd_path: Optional[str] = None
    ) -> Optional[str]:
        """Construye el PKG final usando orbis-pub-cmd.

        Busca el ejecutable orbis-pub-cmd.exe en este orden:
            1. Ruta proporcionada en ``orbis_pub_cmd_path``
            2. Directorio del proyecto
            3. PATH del sistema

        Si no se encuentra, retorna ``None`` y emite una advertencia.

        Args:
            orbis_pub_cmd_path: Ruta explícita al ejecutable orbis-pub-cmd.exe.
                                Si es ``None``, se busca automáticamente.

        Returns:
            Ruta absoluta al archivo PKG generado, o ``None`` si
            orbis-pub-cmd no está disponible.

        Raises:
            RuntimeError: Si orbis-pub-cmd falla durante la ejecución.
        """
        # ── Localizar orbis-pub-cmd ──────────────────────────────────────
        cmd_path = self._find_orbis_pub_cmd(orbis_pub_cmd_path)
        if cmd_path is None:
            logger.warning(
                "orbis-pub-cmd no encontrado. El PKG debe generarse "
                "manualmente usando el archivo GP4 en: %s",
                self.project_dir,
            )
            return None

        logger.info("orbis-pub-cmd encontrado en: %s", cmd_path)

        # ── Buscar el archivo GP4 ────────────────────────────────────────
        gp4_file = os.path.join(
            self.project_dir, f"{self._project_name}.gp4"
        )
        if not os.path.isfile(gp4_file):
            raise FileNotFoundError(
                f"Archivo GP4 no encontrado: '{gp4_file}'. "
                "Ejecute build_project() primero."
            )

        # ── Ruta de salida del PKG ───────────────────────────────────────
        pkg_output_dir = os.path.join(self._output_dir, "pkg")
        os.makedirs(pkg_output_dir, exist_ok=True)
        pkg_output = os.path.join(
            pkg_output_dir,
            f"{self.content_id}.pkg",
        )

        # ── Ejecutar orbis-pub-cmd ───────────────────────────────────────
        cmd_args = [
            cmd_path,
            "img_create",
            "--skip_digest",
            gp4_file,
            pkg_output,
        ]

        logger.info("Ejecutando: %s", " ".join(cmd_args))

        try:
            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                timeout=3600,  # Timeout de 1 hora para ISOs grandes
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"No se pudo ejecutar orbis-pub-cmd: '{cmd_path}'. "
                "Verifique que el archivo sea ejecutable."
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                "orbis-pub-cmd excedió el tiempo límite de 1 hora. "
                "La ISO puede ser demasiado grande."
            )

        if result.returncode != 0:
            logger.error("orbis-pub-cmd stderr: %s", result.stderr)
            raise RuntimeError(
                f"orbis-pub-cmd falló con código {result.returncode}:\n"
                f"{result.stderr.strip()}"
            )

        logger.info("PKG generado exitosamente: %s", pkg_output)

        # Mostrar salida estándar del proceso
        if result.stdout.strip():
            logger.info("orbis-pub-cmd output:\n%s", result.stdout.strip())

        return pkg_output

    def build(self) -> str:
        """Construye el proyecto completo y compila el PKG si orbis-pub-cmd está disponible.

        Returns:
            Ruta al archivo PKG generado (si orbis-pub-cmd tuvo éxito) o al directorio
            del proyecto (si orbis-pub-cmd no está disponible).
        """
        proj_dir = self.build_project()
        pkg_path = self.build_pkg()
        return pkg_path or proj_dir

    def _find_orbis_pub_cmd(
        self, explicit_path: Optional[str] = None
    ) -> Optional[str]:
        """Busca el ejecutable orbis-pub-cmd.exe.

        Orden de búsqueda:
            1. Ruta explícita proporcionada
            2. Directorio del script actual
            3. Directorio del proyecto
            4. PATH del sistema (usando shutil.which)

        Args:
            explicit_path: Ruta explícita al ejecutable.

        Returns:
            Ruta absoluta al ejecutable, o ``None`` si no se encuentra.
        """
        exe_name = "orbis-pub-cmd.exe"

        # 1. Ruta explícita
        if explicit_path:
            if os.path.isfile(explicit_path):
                return os.path.abspath(explicit_path)
            logger.warning(
                "Ruta explícita de orbis-pub-cmd no válida: '%s'",
                explicit_path,
            )

        # 2. Directorio del script actual y raíz del proyecto
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(script_dir, exe_name),
            os.path.join(script_dir, "..", exe_name),
            os.path.join(script_dir, "..", "assets", exe_name),
            os.path.join(self.project_dir, exe_name),
        ]
        for c in candidates:
            norm = os.path.abspath(c)
            if os.path.isfile(norm):
                logger.info("orbis-pub-cmd localizado en: %s", norm)
                return norm

        # 4. PATH del sistema
        found = shutil.which(exe_name)
        if found:
            return os.path.abspath(found)

        return None


# ══════════════════════════════════════════════════════════════════════════════
# Función de conveniencia: conversión rápida
# ══════════════════════════════════════════════════════════════════════════════

def quick_convert(
    iso_path: str,
    output_dir: str,
    eboot_path: Optional[str] = None,
    **kwargs,
) -> str:
    """Conversión rápida en una sola llamada: ISO → estructura de proyecto PKG.

    Toma una ISO de PS2, auto-detecta toda la información posible del juego
    y genera la estructura de directorios completa del proyecto. Los valores
    detectados pueden sobreescribirse vía ``kwargs``.

    Args:
        iso_path: Ruta al archivo ISO de PS2.
        output_dir: Directorio base donde crear el proyecto.
        eboot_path: Ruta al eboot.bin del emulador PS2 (opcional).
        **kwargs: Sobreescrituras opcionales para el proyecto:
            - ``title`` (str): Título del juego.
            - ``title_id`` (str): CUSA ID (e.g. ``"CUSA90001"``).
            - ``content_id`` (str): Content ID completo.
            - ``icon_path`` (str): Ruta a icon0.png personalizado.
            - ``bg_path`` (str): Ruta a pic0.png de fondo.
            - ``startup_image_path`` (str): Ruta a imagen de inicio.
            - ``project_name`` (str): Nombre del proyecto (default: nombre de ISO).

    Returns:
        Ruta absoluta al directorio del proyecto creado.

    Raises:
        FileNotFoundError: Si la ISO no existe.
        ValueError: Si la validación del proyecto falla.

    Ejemplo::

        >>> path = quick_convert(
        ...     "games/shadow_colossus.iso",
        ...     "output",
        ...     eboot_path="tools/eboot.bin",
        ...     title="Shadow of the Colossus",
        ... )
        >>> print(f"Proyecto creado en: {path}")
    """
    if not os.path.isfile(iso_path):
        raise FileNotFoundError(f"Archivo ISO no encontrado: '{iso_path}'")

    # Nombre del proyecto derivado del archivo ISO
    iso_basename = os.path.splitext(os.path.basename(iso_path))[0]
    project_name = kwargs.pop("project_name", iso_basename)

    # Sanitizar el nombre del proyecto (solo caracteres seguros para directorios)
    safe_name = "".join(
        c if (c.isalnum() or c in "._- ") else "_" for c in project_name
    ).strip()
    if not safe_name:
        safe_name = "ps2_project"

    logger.info(
        "quick_convert: ISO='%s', output='%s', project='%s'",
        iso_path,
        output_dir,
        safe_name,
    )

    # ── Crear y configurar el proyecto ───────────────────────────────────
    project = PKGProject(safe_name, output_dir)
    project.iso_paths = [iso_path]

    if eboot_path:
        project.eboot_path = eboot_path

    # Auto-detectar antes de aplicar sobreescrituras
    project.auto_detect()

    # ── Aplicar sobreescrituras del usuario ───────────────────────────────
    _override_fields = {
        "title", "title_id", "content_id", "ps2_game_id",
        "icon_path", "bg_path", "startup_image_path",
    }
    for key, value in kwargs.items():
        if key in _override_fields and value is not None:
            setattr(project, key, value)
            logger.info("Override aplicado: %s = %s", key, value)
        elif key not in _override_fields:
            logger.warning("Parámetro desconocido ignorado: '%s'", key)

    # Regenerar content_id si se cambió title_id manualmente
    if "title_id" in kwargs and "content_id" not in kwargs:
        project.content_id = project.generate_content_id()

    # ── Construir ────────────────────────────────────────────────────────
    project_path = project.build_project()

    logger.info("quick_convert completado: %s", project_path)
    return project_path


# ══════════════════════════════════════════════════════════════════════════════
# Ejecución directa para pruebas
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    # Configurar logging para ver mensajes en consola
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 60)
    print("PKG Builder - Prueba del módulo")
    print("=" * 60)

    # ── Prueba 1: Generación de icono placeholder ────────────────────────
    test_icon_path = os.path.join(
        os.path.dirname(__file__), "test_icon0.png"
    )
    print(f"\n[Test 1] Generando icono placeholder: {test_icon_path}")
    create_placeholder_icon(test_icon_path, "Shadow of the Colossus")
    if os.path.isfile(test_icon_path):
        size = os.path.getsize(test_icon_path)
        print(f"  ✓ Icono generado ({size} bytes)")
        # Verificar que es un PNG válido
        with open(test_icon_path, "rb") as f:
            header = f.read(8)
        assert header == b"\x89PNG\r\n\x1a\n", "Header PNG inválido"
        print("  ✓ Header PNG válido")
        os.remove(test_icon_path)
    else:
        print("  ✗ Error: icono no generado")
        sys.exit(1)

    # ── Prueba 2: Generación de identificadores ──────────────────────────
    print("\n[Test 2] Generación de identificadores")
    project = PKGProject("test_project", "test_output")
    project.ps2_game_id = "SLUS-20001"

    title_id = project.generate_title_id()
    print(f"  Title ID generado: {title_id}")
    assert title_id.startswith("CUSA"), f"Title ID inválido: {title_id}"
    assert len(title_id) == 9, f"Longitud inválida: {len(title_id)}"
    print("  ✓ Title ID válido")

    project.title_id = title_id
    content_id = project.generate_content_id()
    print(f"  Content ID generado: {content_id}")
    assert len(content_id) == 36, f"Longitud inválida: {len(content_id)}"
    assert content_id.startswith("UP9000-"), "Prefijo inválido"
    print("  ✓ Content ID válido")

    # Verificar determinismo: mismo game_id → mismo title_id
    title_id_2 = project.generate_title_id()
    assert title_id == title_id_2, "Title ID no es determinista"
    print("  ✓ Generación determinista verificada")

    # ── Prueba 3: Validación ─────────────────────────────────────────────
    print("\n[Test 3] Validación del proyecto")
    project2 = PKGProject("test", "out")
    errors = project2.validate()
    print(f"  Errores encontrados (esperados): {len(errors)}")
    for err in errors:
        print(f"    - {err}")
    assert len(errors) > 0, "Debería haber errores de validación"
    print("  ✓ Validación detecta campos faltantes correctamente")

    print("\n" + "=" * 60)
    print("Todas las pruebas pasaron ✓")
    print("=" * 60)
