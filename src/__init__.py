"""
PS2 a PS4 - Conversor ISO a PKG
================================

Herramienta para convertir imágenes ISO de PlayStation 2 en paquetes PKG
jugables en PlayStation 4 mediante el emulador PS2 Classics.

Módulos:
    - iso_utils: Lectura y validación de archivos ISO9660 / PS2
    - sfo_builder: Generador de archivos PARAM.SFO para PS4
    - gp4_builder: Generador de archivos de proyecto .gp4
    - config_generator: Generador de configuración del emulador PS2
    - pkg_builder: Ensamblador principal del proyecto PKG
    - gui: Interfaz gráfica de usuario
"""

__version__ = "1.0.0"
__author__ = "ISO-PKG Tool"
__description__ = "Conversor de ISO PS2 a PKG PS4"

from .iso_utils import ISO9660Reader, validate_ps2_iso, get_iso_info
from .sfo_builder import SFOBuilder, create_ps2_classic_sfo
from .gp4_builder import GP4Builder, create_ps2_classic_gp4
from .config_generator import EmulatorConfig, COMPATIBILITY_DB, get_game_config, detect_game_id
from .pkg_builder import PKGProject, quick_convert

__all__ = [
    "ISO9660Reader",
    "validate_ps2_iso",
    "get_iso_info",
    "SFOBuilder",
    "create_ps2_classic_sfo",
    "GP4Builder",
    "create_ps2_classic_gp4",
    "EmulatorConfig",
    "COMPATIBILITY_DB",
    "get_game_config",
    "detect_game_id",
    "PKGProject",
    "quick_convert",
]

