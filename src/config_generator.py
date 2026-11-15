#!/usr/bin/env python3
"""
config_generator.py - Generador de configuración para el emulador PS2 Classics en PS4.

Este módulo genera archivos config-emu-ps4.txt compatibles con el emulador
PS2 Classics que ejecuta juegos PS2 en la consola PS4. Incluye una base de
datos de compatibilidad con parches conocidos para juegos populares y una
función para detectar el ID del juego directamente desde archivos ISO.

Autor: ISO-PKG Tool
"""

import struct
import os
import re
from typing import Optional


# =============================================================================
# Base de datos de compatibilidad
# =============================================================================

COMPATIBILITY_DB: dict[str, dict] = {
    # ── Grand Theft Auto ────────────────────────────────────────────────
    "SLUS-20946": {
        "title": "Grand Theft Auto: San Andreas",
        "config_lines": [
            "--ings-ings-search=ings/icon0.png",
            "--ee-clamping-mode=full",
            "--vu-clamping-mode=full",
            "--iop-sync-interval=16",
            "--gs-fix-hw-offs=1",
        ],
        "lua_patches": [
            '-- Fix streaming stutter\nWriteU32(0x00100000, 0x00000000)',
        ],
        "notes": "Requiere EE/VU clamping completo para evitar cuelgues en misiones.",
    },
    "SLUS-20552": {
        "title": "Grand Theft Auto: Vice City",
        "config_lines": [
            "--ee-clamping-mode=full",
            "--vu-clamping-mode=full",
            "--iop-sync-interval=16",
        ],
        "lua_patches": [],
        "notes": "EE/VU clamping completo necesario para estabilidad general.",
    },
    "SLUS-20062": {
        "title": "Grand Theft Auto III",
        "config_lines": [
            "--ee-clamping-mode=full",
            "--vu-clamping-mode=full",
            "--iop-sync-interval=16",
        ],
        "lua_patches": [],
        "notes": "Estable con clamping completo. Algunos artefactos menores en lluvia.",
    },

    # ── God of War ──────────────────────────────────────────────────────
    "SCUS-97129": {
        "title": "God of War",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=extra+preserve-sign",
            "--gs-uprender=2x2",
            "--gs-fix-hw-offs=1",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "VU clamping extra con preservación de signo evita glitches de geometría.",
    },
    "SCUS-97481": {
        "title": "God of War II",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=extra+preserve-sign",
            "--gs-uprender=2x2",
            "--gs-fix-hw-offs=1",
            "--iop-sync-interval=8",
            "--gs-half-bottom-override=1",
        ],
        "lua_patches": [],
        "notes": "Similar a GoW1. Half-bottom override corrige corte en escenas cinemáticas.",
    },

    # ── Action / Adventure ──────────────────────────────────────────────
    "SLUS-21376": {
        "title": "Bully",
        "config_lines": [
            "--ee-clamping-mode=full",
            "--vu-clamping-mode=normal",
            "--gs-fix-hw-offs=1",
            "--iop-sync-interval=16",
        ],
        "lua_patches": [],
        "notes": "EE clamping completo necesario; sin él se producen cuelgues aleatorios.",
    },
    "SLUS-20228": {
        "title": "Kingdom Hearts",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=normal",
            "--gs-uprender=2x2",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "Funciona bien con configuración estándar. Uprender 2x2 recomendado.",
    },
    "SLUS-21105": {
        "title": "Kingdom Hearts II",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=normal",
            "--gs-uprender=2x2",
            "--gs-fix-hw-offs=1",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "GS HW offset fix corrige alineación de UI en resolución escalada.",
    },
    "SLUS-20672": {
        "title": "Ratchet & Clank: Up Your Arsenal",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=extra+preserve-sign",
            "--gs-fix-hw-offs=1",
            "--gs-half-bottom-override=1",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "VU clamping extra evita geometría rota. Half-bottom para cinemáticas.",
    },
    "SLUS-20965": {
        "title": "Jak 3",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=extra+preserve-sign",
            "--gs-fix-hw-offs=1",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "Requiere VU clamping extra para evitar polígonos deformados.",
    },
    "SCUS-97113": {
        "title": "Shadow of the Colossus",
        "config_lines": [
            "--ee-clamping-mode=full",
            "--vu-clamping-mode=full",
            "--gs-uprender=1x1",
            "--iop-sync-interval=16",
            "--ee-cycle-rate=2",
        ],
        "lua_patches": [],
        "notes": (
            "Juego exigente. Uprender 1x1 recomendado para estabilidad de FPS. "
            "EE cycle rate 2 ayuda con el rendimiento."
        ),
    },
    "SLUS-21044": {
        "title": "Dragon Ball Z: Budokai Tenkaichi 3",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=normal",
            "--gs-fix-hw-offs=1",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "Funcional con configuración estándar. GS fix para UI.",
    },

    # ── RPG / JRPG ─────────────────────────────────────────────────────
    "SLUS-20230": {
        "title": "Final Fantasy X",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=normal",
            "--gs-uprender=2x2",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "Excelente compatibilidad. Funciona sin parches especiales.",
    },
    "SLUS-20510": {
        "title": "Final Fantasy XII",
        "config_lines": [
            "--ee-clamping-mode=full",
            "--vu-clamping-mode=full",
            "--gs-uprender=2x2",
            "--gs-fix-hw-offs=1",
            "--iop-sync-interval=16",
        ],
        "lua_patches": [],
        "notes": "EE/VU clamping completo necesario para evitar crash en áreas grandes.",
    },
    "SCUS-97328": {
        "title": "Ico",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=normal",
            "--gs-uprender=2x2",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "Compatible sin ajustes especiales. Uprender 2x2 mejora visual.",
    },
    "SLUS-21059": {
        "title": "Persona 4",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=normal",
            "--gs-uprender=2x2",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "Excelente compatibilidad sin ajustes adicionales.",
    },
    "SLUS-20614": {
        "title": "Persona 3",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=normal",
            "--gs-uprender=2x2",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "Funciona perfectamente con configuración estándar.",
    },
    "SLUS-21356": {
        "title": "Okami",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=normal",
            "--gs-uprender=2x2",
            "--gs-fix-hw-offs=1",
            "--iop-sync-interval=8",
            "--gs-upscale=Bilinear",
        ],
        "lua_patches": [],
        "notes": "Bilinear upscale recomendado por el estilo artístico cel-shading.",
    },

    # ── Action / Horror ─────────────────────────────────────────────────
    "SLUS-20488": {
        "title": "Devil May Cry 3: Dante's Awakening",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=extra+preserve-sign",
            "--gs-uprender=2x2",
            "--gs-fix-hw-offs=1",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "VU clamping extra para efectos de partículas correctos.",
    },
    "SLUS-20856": {
        "title": "Resident Evil 4",
        "config_lines": [
            "--ee-clamping-mode=full",
            "--vu-clamping-mode=normal",
            "--gs-uprender=2x2",
            "--iop-sync-interval=16",
        ],
        "lua_patches": [],
        "notes": "EE clamping completo evita crash durante escenas con muchos enemigos.",
    },
    "SLUS-20650": {
        "title": "Silent Hill 3",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=normal",
            "--gs-uprender=2x2",
            "--gs-fix-hw-offs=1",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "GS fix para niebla y efectos de post-procesado.",
    },

    # ── Stealth / Tactical ──────────────────────────────────────────────
    "SLUS-20216": {
        "title": "Metal Gear Solid 3: Snake Eater",
        "config_lines": [
            "--ee-clamping-mode=full",
            "--vu-clamping-mode=full",
            "--gs-uprender=2x2",
            "--gs-fix-hw-offs=1",
            "--iop-sync-interval=16",
            "--ee-cycle-rate=2",
        ],
        "lua_patches": [],
        "notes": (
            "Juego exigente. EE/VU clamping completo y cycle rate 2 "
            "mejoran estabilidad y rendimiento en áreas densas."
        ),
    },

    # ── Fighting ────────────────────────────────────────────────────────
    "SLUS-20234": {
        "title": "Tekken 5",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=normal",
            "--gs-uprender=2x2",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "Buena compatibilidad. Sin problemas conocidos.",
    },
    "SLUS-21386": {
        "title": "Mortal Kombat: Armageddon",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=normal",
            "--gs-uprender=2x2",
            "--gs-fix-hw-offs=1",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "GS fix para alineación de barras de vida en escalado.",
    },

    # ── Sports / Extreme ────────────────────────────────────────────────
    "SLUS-20199": {
        "title": "Burnout 3: Takedown",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=extra+preserve-sign",
            "--gs-uprender=2x2",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "VU clamping extra para evitar explosiones con geometría rota.",
    },

    # ── Racing ──────────────────────────────────────────────────────────
    "SLUS-20449": {
        "title": "Need for Speed: Underground",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=normal",
            "--gs-uprender=2x2",
            "--gs-fix-hw-offs=1",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "Compatible. GS fix para HUD en resoluciones escaladas.",
    },
    "SLUS-20636": {
        "title": "Need for Speed: Underground 2",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=normal",
            "--gs-uprender=2x2",
            "--gs-fix-hw-offs=1",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "Similar a NFS Underground 1. Sin problemas significativos.",
    },

    # ── Anime / Misc ────────────────────────────────────────────────────
    "SLUS-20731": {
        "title": "Naruto: Ultimate Ninja 3",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=normal",
            "--gs-uprender=2x2",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "Funciona correctamente con configuración estándar.",
    },
    "SLUS-20977": {
        "title": "Guitar Hero II",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=normal",
            "--gs-uprender=2x2",
            "--iop-sync-interval=8",
            "--host-audio=1",
        ],
        "lua_patches": [],
        "notes": "Audio host habilitado es crítico para sincronización de notas.",
    },

    # ── Tony Hawk (nota: SLUS-20062 es GTA III; usamos ID correcto) ───
    "SLUS-20363": {
        "title": "Tony Hawk's Pro Skater 3",
        "config_lines": [
            "--ee-clamping-mode=normal",
            "--vu-clamping-mode=normal",
            "--gs-uprender=2x2",
            "--iop-sync-interval=8",
        ],
        "lua_patches": [],
        "notes": "Sin problemas conocidos. Buen rendimiento general.",
    },
}


# =============================================================================
# Constantes de validación
# =============================================================================

_VALID_UPRENDER = ("1x1", "2x2", "3x3", "4x4")
_VALID_UPSCALE = ("EdgeSmooth", "Bilinear", "None")
_VALID_DISPLAY_MODES = ("full", "window")
_VALID_SCANLINES = ("None", "Light", "CRT")
_MAX_DISCS = 5
_MIN_DISCS = 1

# Tamaño de sector ISO 9660
_ISO_SECTOR_SIZE = 2048


# =============================================================================
# Clase EmulatorConfig
# =============================================================================

class EmulatorConfig:
    """Generador de configuración para el emulador PS2 Classics en PS4.

    Crea archivos ``config-emu-ps4.txt`` con los parámetros necesarios para
    ejecutar juegos PS2 dentro del emulador integrado de la PS4.

    Attributes:
        ps2_title_id: Identificador del título PS2 (e.g. ``"SLUS-20946"``).
        num_discs: Número de discos del juego (1-5).
        trophy_support: Habilitar soporte de trofeos.
        gs_uprender: Resolución de renderizado GS (``"1x1"``, ``"2x2"``, ``"3x3"``, ``"4x4"``).
        gs_upscale: Método de escalado GS (``"EdgeSmooth"``, ``"Bilinear"``, ``"None"``).
        widescreen: Habilitar modo pantalla ancha 16:9 real.
        deblur: Eliminar desenfoque analógico de la PS2 original.
        fps_60: Forzar o desbloquear 60 FPS estables.
        force_progressive: Forzar señal progresiva 480p (evita entrelazado 480i).
        mtvu: Habilitar Multi-Threaded VU1 para exprimir CPUs multinúcleo.
        scanlines: Filtro de líneas de escaneo (``"None"``, ``"Light"``, ``"CRT"``).
        host_audio: Habilitar audio del host.
        host_display_mode: Modo de visualización (``"full"`` o ``"window"``).
        custom_patches: Líneas de configuración adicionales personalizadas.

    Example:
        >>> cfg = EmulatorConfig("SLUS-20946", gs_render="3x3", widescreen=True, fps_60=True)
        >>> cfg.save("config-emu-ps4.txt")
    """

    def __init__(
        self,
        ps2_title_id: str = "SLUS-20946",
        num_discs: int = 1,
        gs_render: Optional[str] = None,
        gs_scale: Optional[str] = None,
        fullscreen: bool = True,
        trophies: bool = False,
        widescreen: bool = False,
        host_audio: bool = True,
        deblur: bool = False,
        fps_60: bool = False,
        force_progressive: bool = False,
        mtvu: bool = True,
        scanlines: str = "None",
        custom_patches: Optional[list[str] | str] = None,
        **kwargs,
    ) -> None:
        """Inicializa la configuración del emulador con modificadores gráficos."""
        # Soporte para title id flexible
        if not re.match(r"^[A-Z]{4}-\d{5}$", str(ps2_title_id).strip().upper()):
            self._ps2_title_id = "SLUS-20946"
        else:
            self._ps2_title_id = str(ps2_title_id).strip().upper()

        self.num_discs = num_discs
        self.trophy_support: bool = trophies or kwargs.get("trophy_support", False)
        
        render_val = gs_render or kwargs.get("gs_uprender", "2x2")
        self.gs_uprender = render_val if render_val in _VALID_UPRENDER else "2x2"

        scale_val = gs_scale or kwargs.get("gs_upscale", "EdgeSmooth")
        self.gs_upscale = scale_val if scale_val in _VALID_UPSCALE else "EdgeSmooth"

        self.widescreen: bool = widescreen
        self.deblur: bool = deblur or kwargs.get("remove_blur", False)
        self.fps_60: bool = fps_60 or kwargs.get("unlock_fps", False)
        self.force_progressive: bool = force_progressive
        self.mtvu: bool = mtvu
        self.scanlines: str = scanlines if scanlines in _VALID_SCANLINES else "None"

        self.host_audio: bool = host_audio
        self.host_display_mode: str = "full" if fullscreen else "window"

        # Procesar parches personalizados
        if isinstance(custom_patches, str):
            self.custom_patches: list[str] = [
                p.strip() for p in custom_patches.splitlines() if p.strip()
            ]
        elif isinstance(custom_patches, list):
            self.custom_patches = list(custom_patches)
        else:
            self.custom_patches = []

    # ── Propiedades con validación ──────────────────────────────────────

    @property
    def ps2_title_id(self) -> str:
        """ID del título PS2 (e.g. ``'SLUS-20946'``)."""
        return self._ps2_title_id

    @ps2_title_id.setter
    def ps2_title_id(self, value: str) -> None:
        raw = str(value).strip().upper()
        # Normalizar automáticamente formatos como SLES_549.52 o SLES54952 a SLES-54952
        cleaned = raw.replace("_", "").replace(".", "").replace("-", "")
        if len(cleaned) == 9 and cleaned[:4].isalpha() and cleaned[4:].isdigit():
            normalized = f"{cleaned[:4]}-{cleaned[4:]}"
        else:
            normalized = raw

        pattern = r"^[A-Z]{4}-\d{5}$"
        if not re.match(pattern, normalized):
            # Fallback seguro para IDs con sufijos especiales
            normalized = "SLUS-20946"

        self._ps2_title_id = normalized

    @property
    def num_discs(self) -> int:
        """Número de discos del juego (1–5)."""
        return self._num_discs

    @num_discs.setter
    def num_discs(self, value: int) -> None:
        if not isinstance(value, int) or not (_MIN_DISCS <= value <= _MAX_DISCS):
            raise ValueError(
                f"num_discs debe ser un entero entre {_MIN_DISCS} y {_MAX_DISCS}, "
                f"se recibió: {value!r}"
            )
        self._num_discs = value

    @property
    def gs_uprender(self) -> str:
        """Resolución de renderizado GS."""
        return self._gs_uprender

    @gs_uprender.setter
    def gs_uprender(self, value: str) -> None:
        if value not in _VALID_UPRENDER:
            raise ValueError(
                f"gs_uprender inválido: '{value}'. "
                f"Opciones válidas: {_VALID_UPRENDER}"
            )
        self._gs_uprender = value

    @property
    def gs_upscale(self) -> str:
        """Método de escalado GS."""
        return self._gs_upscale

    @gs_upscale.setter
    def gs_upscale(self, value: str) -> None:
        if value not in _VALID_UPSCALE:
            raise ValueError(
                f"gs_upscale inválido: '{value}'. "
                f"Opciones válidas: {_VALID_UPSCALE}"
            )
        self._gs_upscale = value

    @property
    def host_display_mode(self) -> str:
        """Modo de visualización del host."""
        return self._host_display_mode

    @host_display_mode.setter
    def host_display_mode(self, value: str) -> None:
        if value not in _VALID_DISPLAY_MODES:
            raise ValueError(
                f"host_display_mode inválido: '{value}'. "
                f"Opciones válidas: {_VALID_DISPLAY_MODES}"
            )
        self._host_display_mode = value

    # ── Generación de configuración ─────────────────────────────────────

    def generate_config(self) -> str:
        """Genera el contenido del archivo config-emu-ps4.txt.

        Returns:
            Cadena con todas las líneas de configuración del emulador,
            lista para escribir a disco.
        """
        lines: list[str] = [
            '--path-patches="/app0/patches"',
            '--path-trophydata="/app0/trophy_data"',
            '--path-featuredata="/app0/feature_data"',
            f"--ps2-title-id={self._ps2_title_id}",
            f"--max-disc-num={self._num_discs}",
            f"--trophy-support={1 if self.trophy_support else 0}",
            f"--gs-uprender={self._gs_uprender}",
            f"--gs-upscale={self._gs_upscale}",
            f"--host-audio={1 if self.host_audio else 0}",
            f"--host-display-mode={self._host_display_mode}",
        ]

        # ── Modificadores gráficos avanzados ──────────────────────────────
        # Pantalla ancha nativa 16:9
        if self.widescreen:
            lines.append("--widescreen=1")

        # Eliminación de desenfoque analógico de PS2 (De-Blur HD)
        if self.deblur:
            lines.append("--gs-deblur=1")
            lines.append("--gs-kernel=sharp")

        # Desbloqueo / Forzado de 60 FPS estables
        if self.fps_60:
            lines.append("--framerate=60")
            lines.append("--iop-sync-interval=4")

        # Modo Progresivo 480p nativo (elimina artefactos de entrelazado 480i)
        if self.force_progressive:
            lines.append("--force-progressive=1")

        # Aceleración Multi-hilo VU1 (aprovecha núcleos extra de CPU)
        if self.mtvu:
            lines.append("--mtvu=1")

        # Shaders retro de líneas de escaneo / CRT
        if self.scanlines == "Light":
            lines.append("--scanline-shader=1")
            lines.append("--scanline-brightness=80")
        elif self.scanlines == "CRT":
            lines.append("--scanline-shader=1")
            lines.append("--scanline-brightness=60")

        # Líneas de configuración personalizadas
        for patch_line in self.custom_patches:
            stripped = patch_line.strip()
            if stripped:
                lines.append(stripped)

        # ROM entries: disc01.iso, disc02.iso, …
        for disc_num in range(1, self._num_discs + 1):
            lines.append(f'--rom="disc{disc_num:02d}.iso"')

        return "\n".join(lines) + "\n"

    def to_string(self) -> str:
        """Alias para generate_config()."""
        return self.generate_config()

    def to_file(self, output_path: str) -> None:
        """Alias para save()."""
        self.save(output_path)

    def apply_compatibility_patches(self, game_id: Optional[str] = None) -> bool:
        """Aplica parches de compatibilidad de la base de datos interna.

        Busca el juego en ``COMPATIBILITY_DB`` y agrega las líneas de
        configuración recomendadas a ``custom_patches``.

        Args:
            game_id: ID del juego a buscar. Si es ``None``, usa
                ``self.ps2_title_id``.

        Returns:
            ``True`` si se encontraron y aplicaron parches, ``False`` si el
            juego no está en la base de datos.
        """
        lookup_id = game_id or self._ps2_title_id
        entry = get_game_config(lookup_id)
        if entry is None:
            return False

        # Agregar líneas de compatibilidad sin duplicar
        existing = set(self.custom_patches)
        for line in entry.get("config_lines", []):
            if line not in existing:
                self.custom_patches.append(line)
                existing.add(line)

        return True

    def save(self, output_path: str) -> None:
        """Escribe la configuración generada a un archivo.

        Args:
            output_path: Ruta del archivo de salida.

        Raises:
            OSError: Si no se puede escribir en la ruta especificada.
        """
        content = self.generate_config()
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

    def __repr__(self) -> str:
        return (
            f"EmulatorConfig(ps2_title_id={self._ps2_title_id!r}, "
            f"num_discs={self._num_discs}, "
            f"gs_uprender={self._gs_uprender!r}, "
            f"widescreen={self.widescreen})"
        )


# =============================================================================
# Funciones auxiliares
# =============================================================================

def get_game_config(game_id: str) -> Optional[dict]:
    """Busca un juego en la base de datos de compatibilidad.

    Args:
        game_id: ID del título PS2 (e.g. ``"SLUS-20946"``).

    Returns:
        Diccionario con claves ``title``, ``config_lines``, ``lua_patches``
        y ``notes`` si el juego existe; ``None`` en caso contrario.
    """
    normalized = game_id.strip().upper()
    return COMPATIBILITY_DB.get(normalized)


def detect_game_id(iso_path: str) -> Optional[str]:
    """Detecta el ID del juego PS2 leyendo SYSTEM.CNF desde un archivo ISO.

    Implementa lectura manual de ISO 9660 (Primary Volume Descriptor y
    directorio raíz) para localizar y leer el archivo SYSTEM.CNF sin
    dependencias externas.

    El archivo SYSTEM.CNF contiene una línea como:
        ``BOOT2 = cdrom0:\\SLUS_209.46;1``
    de la cual se extrae el ID normalizado ``"SLUS-20946"``.

    Args:
        iso_path: Ruta al archivo ISO del juego PS2.

    Returns:
        ID del juego en formato ``"XXXX-NNNNN"`` (e.g. ``"SLUS-20946"``),
        o ``None`` si no se pudo detectar.

    Raises:
        FileNotFoundError: Si el archivo ISO no existe.
        OSError: Si ocurre un error de lectura.
    """
    if not os.path.isfile(iso_path):
        raise FileNotFoundError(f"Archivo ISO no encontrado: {iso_path}")

    with open(iso_path, "rb") as f:
        # ── Paso 1: Leer el Primary Volume Descriptor (PVD) ────────────
        # El PVD se encuentra en el sector 16 (offset 0x8000 = 32768).
        pvd_offset = 16 * _ISO_SECTOR_SIZE
        f.seek(pvd_offset)
        pvd = f.read(_ISO_SECTOR_SIZE)

        if len(pvd) < _ISO_SECTOR_SIZE:
            return None

        # Verificar firma del PVD: byte 0 = 0x01, bytes 1-5 = "CD001"
        if pvd[0:1] != b"\x01" or pvd[1:6] != b"CD001":
            return None

        # ── Paso 2: Extraer el registro del directorio raíz ────────────
        # El Directory Record del directorio raíz está en los bytes
        # 156–189 del PVD (34 bytes).
        root_dir_record = pvd[156:190]

        # Extent Location del directorio raíz (Little-Endian, bytes 2-5)
        root_lba = struct.unpack_from("<I", root_dir_record, 2)[0]
        # Data Length del directorio raíz (Little-Endian, bytes 10-13)
        root_size = struct.unpack_from("<I", root_dir_record, 10)[0]

        # ── Paso 3: Leer el directorio raíz y buscar SYSTEM.CNF ────────
        f.seek(root_lba * _ISO_SECTOR_SIZE)
        root_data = f.read(root_size)

        system_cnf_lba, system_cnf_size = _find_file_in_directory(
            root_data, "SYSTEM.CNF"
        )

        if system_cnf_lba is None:
            return None

        # ── Paso 4: Leer el contenido de SYSTEM.CNF ────────────────────
        f.seek(system_cnf_lba * _ISO_SECTOR_SIZE)
        cnf_data = f.read(system_cnf_size)
        cnf_text = cnf_data.decode("ascii", errors="replace")

        # ── Paso 5: Parsear la línea BOOT2 ─────────────────────────────
        return _parse_boot2_line(cnf_text)


def _find_file_in_directory(
    dir_data: bytes, target_name: str
) -> tuple[Optional[int], Optional[int]]:
    """Busca un archivo en los datos de un directorio ISO 9660.

    Itera los registros de directorio y busca por nombre de archivo,
    ignorando versión (``";1"``).

    Args:
        dir_data: Datos binarios del directorio.
        target_name: Nombre del archivo a buscar (sin versión).

    Returns:
        Tupla ``(lba, size)`` con la ubicación y tamaño del archivo,
        o ``(None, None)`` si no se encontró.
    """
    target_upper = target_name.upper()
    offset = 0

    while offset < len(dir_data):
        # Longitud del registro de directorio
        record_len = dir_data[offset]

        if record_len == 0:
            # Fin de los registros en este sector; avanzar al siguiente
            next_sector = ((offset // _ISO_SECTOR_SIZE) + 1) * _ISO_SECTOR_SIZE
            if next_sector >= len(dir_data):
                break
            offset = next_sector
            continue

        if offset + record_len > len(dir_data):
            break

        record = dir_data[offset : offset + record_len]

        # Extent Location (Little-Endian) — bytes 2-5 del record
        file_lba = struct.unpack_from("<I", record, 2)[0]
        # Data Length (Little-Endian) — bytes 10-13 del record
        file_size = struct.unpack_from("<I", record, 10)[0]
        # File Identifier Length — byte 32
        name_len = record[32]

        if name_len > 0 and 33 + name_len <= len(record):
            # Nombre del archivo (puede incluir ";1" para la versión)
            raw_name = record[33 : 33 + name_len].decode("ascii", errors="replace")
            # Quitar versión: "SYSTEM.CNF;1" -> "SYSTEM.CNF"
            clean_name = raw_name.split(";")[0].strip().upper()

            if clean_name == target_upper:
                return file_lba, file_size

        offset += record_len

    return None, None


def _parse_boot2_line(cnf_text: str) -> Optional[str]:
    """Extrae y normaliza el ID del juego de la línea BOOT2 de SYSTEM.CNF.

    Busca una línea con el formato:
        ``BOOT2 = cdrom0:\\SLUS_209.46;1``
    y devuelve el ID normalizado ``"SLUS-20946"``.

    Args:
        cnf_text: Contenido textual del archivo SYSTEM.CNF.

    Returns:
        ID del juego normalizado o ``None`` si no se encuentra.
    """
    for line in cnf_text.splitlines():
        line = line.strip()
        if not line.upper().startswith("BOOT2"):
            continue

        # Extraer la parte después del '='
        parts = line.split("=", 1)
        if len(parts) < 2:
            continue

        boot_path = parts[1].strip()

        # Extraer el nombre del ejecutable: e.g. "SLUS_209.46"
        # Patrón: busca XXXX_NNN.NN al final de la ruta
        match = re.search(
            r"([A-Za-z]{4}[_-]\d{3}\.\d{2})", boot_path
        )
        if match:
            raw_id = match.group(1).upper()
            # Convertir "SLUS_209.46" -> "SLUS-20946"
            prefix = raw_id[:4]          # "SLUS"
            numbers = raw_id[5:]          # "209.46"
            numbers = numbers.replace(".", "")  # "20946"
            return f"{prefix}-{numbers}"

    return None


# =============================================================================
# Ejecución directa (ejemplo / prueba rápida)
# =============================================================================

if __name__ == "__main__":
    # Ejemplo de uso
    config = EmulatorConfig("SLUS-20946", num_discs=1)
    config.apply_compatibility_patches()
    print(config.generate_config())
    print(f"Juego: {get_game_config('SLUS-20946')}")
