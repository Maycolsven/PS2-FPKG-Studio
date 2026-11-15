#!/usr/bin/env python3
"""
config_generator.py - Generador de configuración para el emulador PS2 Classics en PS4.
Sincronizado con los parámetros internos de assets/eboot.bin (Jak1-TPL build).
"""

import os
import re
import struct
from typing import Optional

COMPATIBILITY_DB: dict[str, dict] = {
    "SLUS-21661": {
        "title": "Ben 10: Protector of Earth",
        "status": "Jugable",
        "config_lines": [
            "--gs-uprender=2x2",
            "--gs-upscale=edgesmooth",
            "--ee-cycle-scalar=1.2",
            "--vu1-no-clamping=0",
        ],
        "lua_patches": [],
        "notes": "Funciona fluido con escalado 2x2 y ajuste de ciclo EE en 1.2.",
    },
    "SLES-54957": {
        "title": "Ben 10: Protector of Earth (EUR)",
        "status": "Jugable",
        "config_lines": [
            "--gs-uprender=2x2",
            "--gs-upscale=edgesmooth",
            "--ee-cycle-scalar=1.2",
            "--force-pal-60hz=1",
        ],
        "lua_patches": [],
        "notes": "Versión PAL. Se recomienda forzar 60Hz.",
    },
    "SLUS-20946": {
        "title": "Grand Theft Auto: San Andreas",
        "status": "Perfecto",
        "config_lines": [
            "--fpu-no-clamping=0",
            "--fpu-clamp-results=1",
            "--vu0-no-clamping=0",
            "--vu1-no-clamping=0",
            "--ee-cycle-scalar=1.5",
        ],
        "lua_patches": [],
        "notes": "Clamping FPU/VU activado para evitar cuelgues en misiones.",
    },
    "SLUS-20552": {
        "title": "Grand Theft Auto: Vice City",
        "status": "Perfecto",
        "config_lines": [
            "--fpu-no-clamping=0",
            "--fpu-clamp-results=1",
            "--vu0-no-clamping=0",
            "--vu1-no-clamping=0",
        ],
        "lua_patches": [],
        "notes": "Clamping FPU/VU necesario para estabilidad general.",
    },
    "SLUS-20062": {
        "title": "Grand Theft Auto III",
        "status": "Perfecto",
        "config_lines": [
            "--fpu-no-clamping=0",
            "--fpu-clamp-results=1",
            "--vu0-no-clamping=0",
            "--vu1-no-clamping=0",
        ],
        "lua_patches": [],
        "notes": "Estable con clamping FPU/VU.",
    },
    "SCUS-97129": {
        "title": "God of War",
        "status": "Jugable",
        "config_lines": [
            "--gs-uprender=2x2",
            "--gs-upscale=edgesmooth",
            "--vu1-no-clamping=0",
            "--vu1-clamp-results=1",
        ],
        "lua_patches": [],
        "notes": "VU1 clamping evita glitches de geometría.",
    },
    "SCUS-97481": {
        "title": "God of War II",
        "status": "Jugable",
        "config_lines": [
            "--gs-uprender=2x2",
            "--gs-upscale=edgesmooth",
            "--vu1-no-clamping=0",
            "--vu1-clamp-results=1",
        ],
        "lua_patches": [],
        "notes": "Similar a GoW1. Excelente rendimiento con 2x2.",
    },
    "SLUS-21376": {
        "title": "Bully",
        "status": "Perfecto",
        "config_lines": [
            "--fpu-no-clamping=0",
            "--fpu-clamp-results=1",
            "--ee-cycle-scalar=1.2",
        ],
        "lua_patches": [],
        "notes": "FPU clamping evita cuelgues aleatorios.",
    },
    "SLUS-20228": {
        "title": "Kingdom Hearts",
        "status": "Perfecto",
        "config_lines": [
            "--gs-uprender=2x2",
            "--gs-upscale=edgesmooth",
        ],
        "lua_patches": [],
        "notes": "Funciona bien con configuración estándar. Uprender 2x2 recomendado.",
    },
    "SLUS-21105": {
        "title": "Kingdom Hearts II",
        "status": "Perfecto",
        "config_lines": [
            "--gs-uprender=2x2",
            "--gs-upscale=edgesmooth",
        ],
        "lua_patches": [],
        "notes": "Excelente compatibilidad en 2x2.",
    },
    "SCUS-97113": {
        "title": "Shadow of the Colossus",
        "status": "Jugable",
        "config_lines": [
            "--gs-uprender=none",
            "--ee-cycle-scalar=2.0",
            "--iop-cycle-scalar=1.5",
        ],
        "lua_patches": [],
        "notes": "Juego exigente. EE cycle scalar 2.0 mejora la estabilidad de FPS.",
    },
    "SLUS-21044": {
        "title": "Dragon Ball Z: Budokai Tenkaichi 3",
        "status": "Perfecto",
        "config_lines": [
            "--gs-uprender=2x2",
            "--gs-upscale=edgesmooth",
        ],
        "lua_patches": [],
        "notes": "Funcional con configuración estándar.",
    },
    "SLUS-20652": {
        "title": "Downhill Domination",
        "status": "Perfecto",
        "config_lines": [
            "--gs-uprender=2x2",
            "--gs-upscale=edgesmooth",
            "--ee-cycle-scalar=1.2",
        ],
        "lua_patches": [],
        "notes": "Muy fluido a 60 FPS con escalado 2x2.",
    },
    "SLUS-20856": {
        "title": "Resident Evil 4",
        "status": "Perfecto",
        "config_lines": [
            "--fpu-no-clamping=0",
            "--fpu-clamp-results=1",
            "--gs-uprender=2x2",
        ],
        "lua_patches": [],
        "notes": "FPU clamping evita crash durante escenas con muchos enemigos.",
    },
}

# Valores reales aceptados por assets/eboot.bin
_VALID_UPRENDER = ("none", "2x2")
_VALID_UPSCALE = ("edgesmooth", "motionvec", "gpu", "none")
_VALID_DISPLAY_MODES = ("full", "16:9", "4:3", "normal")
_MAX_DISCS = 5
_MIN_DISCS = 1
_ISO_SECTOR_SIZE = 2048


class EmulatorConfig:
    """Generador de config-emu-ps4.txt sincronizado con los flags reales del eboot.bin."""

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
        lua_patches: Optional[list[str]] = None,
        **kwargs,
    ) -> None:
        self.ps2_title_id = ps2_title_id
        self.num_discs = num_discs
        self.trophy_support: bool = trophies or kwargs.get("trophy_support", False)

        # Normalizar gs_uprender a valores válidos del binario ("none" o "2x2")
        render_val = str(gs_render or kwargs.get("gs_uprender", "2x2")).lower()
        if render_val in ("1x1", "none"):
            self.gs_uprender = "none"
        else:
            self.gs_uprender = "2x2"

        # Normalizar gs_upscale a minúsculas válidas del binario
        scale_val = str(gs_scale or kwargs.get("gs_upscale", "edgesmooth")).lower()
        if scale_val == "bilinear":
            scale_val = "gpu"
        self.gs_upscale = scale_val if scale_val in _VALID_UPSCALE else "edgesmooth"

        self.widescreen: bool = widescreen
        self.deblur: bool = deblur or kwargs.get("remove_blur", False)
        self.fps_60: bool = fps_60 or kwargs.get("unlock_fps", False)
        self.force_progressive: bool = force_progressive
        self.mtvu: bool = mtvu
        self.scanlines: str = scanlines
        self.host_audio: bool = host_audio
        self.host_display_mode: str = "16:9" if widescreen else ("full" if fullscreen else "4:3")

        if isinstance(custom_patches, str):
            self.custom_patches: list[str] = [
                p.strip() for p in custom_patches.splitlines()
                if p.strip() and not p.strip().startswith("#")
            ]
        elif isinstance(custom_patches, list):
            self.custom_patches = list(custom_patches)
        else:
            self.custom_patches = []

        self.lua_patches: list[str] = list(lua_patches) if lua_patches else []

    @property
    def ps2_title_id(self) -> str:
        return self._ps2_title_id

    @ps2_title_id.setter
    def ps2_title_id(self, value: str) -> None:
        raw = str(value).strip().upper()
        cleaned = raw.replace("_", "").replace(".", "").replace("-", "")
        if len(cleaned) == 9 and cleaned[:4].isalpha() and cleaned[4:].isdigit():
            normalized = f"{cleaned[:4]}-{cleaned[4:]}"
        else:
            normalized = raw
        if not re.match(r"^[A-Z]{4}-\d{5}$", normalized):
            normalized = "SLUS-20946"
        self._ps2_title_id = normalized

    @property
    def num_discs(self) -> int:
        return self._num_discs

    @num_discs.setter
    def num_discs(self, value: int) -> None:
        if not isinstance(value, int) or not (_MIN_DISCS <= value <= _MAX_DISCS):
            raise ValueError(f"num_discs debe estar entre {_MIN_DISCS} y {_MAX_DISCS}")
        self._num_discs = value

    @property
    def gs_uprender(self) -> str:
        return self._gs_uprender

    @gs_uprender.setter
    def gs_uprender(self, value: str) -> None:
        val = value.lower()
        self._gs_uprender = "none" if val in ("1x1", "none") else "2x2"

    @property
    def gs_upscale(self) -> str:
        return self._gs_upscale

    @gs_upscale.setter
    def gs_upscale(self, value: str) -> None:
        val = value.lower()
        if val == "bilinear":
            val = "gpu"
        self._gs_upscale = val if val in _VALID_UPSCALE else "edgesmooth"

    def generate_config(self) -> str:
        """Genera config-emu-ps4.txt usando exclusivamente flags soportados por eboot.bin."""
        lines: list[str] = [
            '--path-patches="/app0/patches"',
            '--path-trophydata="/app0/trophy_data"',
            '--path-featuredata="/app0/feature_data"',
            '--path-toolingscript="/app0/patches"',
            f"--ps2-title-id={self._ps2_title_id}",
            f"--max-disc-num={self._num_discs}",
            f"--trophy-support={1 if self.trophy_support else 0}",
            f"--gs-uprender={self._gs_uprender}",
            f"--gs-upscale={self._gs_upscale}",
            f"--host-audio={1 if self.host_audio else 0}",
            f"--host-display-mode={self.host_display_mode}",
        ]

        if self.force_progressive:
            lines.append("--gs-progressive=1")

        if self.deblur:
            lines.append("--gs-force-bilinear=1")

        if self.fps_60:
            lines.append("--framelimit-fps=60.0")
            lines.append("--force-pal-60hz=1")

        if self.mtvu:
            lines.append("--threaded-gs=1")

        # Agregar parches personalizados evitando duplicar claves existentes
        existing_keys = {line.split("=", 1)[0] for line in lines if "=" in line}
        for patch_line in self.custom_patches:
            stripped = patch_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key = stripped.split("=", 1)[0]
            if key not in existing_keys:
                lines.append(stripped)
                existing_keys.add(key)

        return "\n".join(lines) + "\n"

    def to_string(self) -> str:
        return self.generate_config()

    def to_file(self, output_path: str) -> None:
        self.save(output_path)

    def apply_compatibility_patches(self, game_id: Optional[str] = None) -> bool:
        lookup_id = game_id or self._ps2_title_id
        entry = get_game_config(lookup_id)
        if entry is None:
            return False

        existing = set(self.custom_patches)
        for line in entry.get("config_lines", []):
            if line not in existing:
                self.custom_patches.append(line)
                existing.add(line)

        for lua in entry.get("lua_patches", []):
            if lua not in self.lua_patches:
                self.lua_patches.append(lua)

        return True

    def generate_lua_script(self) -> Optional[str]:
        """Genera el contenido de <GAME_ID>_config.lua si existen parches Lua."""
        if not self.lua_patches:
            return None
        header = [
            "-- Auto-generated Lua Patch for PS2 Classics Emulator",
            "apiRequest(0.1)",
            "local eeObj = getEEObject()",
            "local emuObj = getEmuObject()",
            "local patcher = function()",
        ]
        body = [f"    {line}" for patch in self.lua_patches for line in patch.splitlines()]
        footer = [
            "end",
            "emuObj.AddVsyncHook(patcher)",
            "",
        ]
        return "\n".join(header + body + footer)

    def save(self, output_path: str) -> None:
        content = self.generate_config()
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)


def convert_pnach_to_lua(pnach_text: str) -> list[str]:
    """Convierte líneas patch=1,EE,ADDR,extended,VAL de PCSX2 (.pnach) a instrucciones Lua."""
    lua_lines: list[str] = []
    pattern = re.compile(
        r"^patch\s*=\s*1\s*,\s*EE\s*,\s*([0-9A-Fa-f]+)\s*,\s*(?:extended|word)\s*,\s*([0-9A-Fa-f]+)",
        re.IGNORECASE,
    )
    for raw_line in pnach_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        match = pattern.match(line)
        if match:
            addr, val = match.group(1).upper(), match.group(2).upper()
            # Convertir prefijos de código PS2 (2xxxxxxx = 32-bit write -> 0x0xxxxxxx)
            if len(addr) == 8 and addr.startswith("2"):
                addr = "0" + addr[1:]
            lua_lines.append(f"eeObj.WriteMem32(0x{addr}, 0x{val})")
    return lua_lines


def get_game_config(game_id: str) -> Optional[dict]:
    if not game_id:
        return None
    raw = game_id.strip().upper().replace("_", "-").replace(".", "")
    if len(raw) == 9 and "-" not in raw:
        raw = f"{raw[:4]}-{raw[4:]}"
    return COMPATIBILITY_DB.get(raw)


def detect_game_id(iso_path: str) -> Optional[str]:
    if not os.path.isfile(iso_path):
        raise FileNotFoundError(f"Archivo ISO no encontrado: {iso_path}")

    with open(iso_path, "rb") as f:
        pvd_offset = 16 * _ISO_SECTOR_SIZE
        f.seek(pvd_offset)
        pvd = f.read(_ISO_SECTOR_SIZE)
        if len(pvd) < _ISO_SECTOR_SIZE or pvd[0:1] != b"\x01" or pvd[1:6] != b"CD001":
            return None

        root_dir_record = pvd[156:190]
        root_lba = struct.unpack_from("<I", root_dir_record, 2)[0]
        root_size = struct.unpack_from("<I", root_dir_record, 10)[0]

        f.seek(root_lba * _ISO_SECTOR_SIZE)
        root_data = f.read(root_size)

        system_cnf_lba, system_cnf_size = _find_file_in_directory(root_data, "SYSTEM.CNF")
        if system_cnf_lba is None:
            return None

        f.seek(system_cnf_lba * _ISO_SECTOR_SIZE)
        cnf_data = f.read(system_cnf_size)
        cnf_text = cnf_data.decode("ascii", errors="replace")
        return _parse_boot2_line(cnf_text)


def _find_file_in_directory(dir_data: bytes, target_name: str) -> tuple[Optional[int], Optional[int]]:
    target_upper = target_name.upper()
    offset = 0
    while offset < len(dir_data):
        record_len = dir_data[offset]
        if record_len == 0:
            next_sector = ((offset // _ISO_SECTOR_SIZE) + 1) * _ISO_SECTOR_SIZE
            if next_sector >= len(dir_data):
                break
            offset = next_sector
            continue
        if offset + record_len > len(dir_data):
            break
        record = dir_data[offset : offset + record_len]
        file_lba = struct.unpack_from("<I", record, 2)[0]
        file_size = struct.unpack_from("<I", record, 10)[0]
        name_len = record[32]
        if name_len > 0 and 33 + name_len <= len(record):
            raw_name = record[33 : 33 + name_len].decode("ascii", errors="replace")
            clean_name = raw_name.split(";")[0].strip().rstrip(".").upper()
            if clean_name == target_upper:
                return file_lba, file_size
        offset += record_len
    return None, None


def _parse_boot2_line(cnf_text: str) -> Optional[str]:
    for line in cnf_text.splitlines():
        line = line.strip()
        if not line.upper().startswith("BOOT2"):
            continue
        parts = line.split("=", 1)
        if len(parts) < 2:
            continue
        match = re.search(r"([A-Za-z]{4}[_-]\d{3}\.\d{2})", parts[1].strip())
        if match:
            raw_id = match.group(1).upper()
            prefix = raw_id[:4]
            numbers = raw_id[5:].replace(".", "")
            return f"{prefix}-{numbers}"
    return None