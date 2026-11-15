"""
pkg_builder.py - Módulo principal de ensamblaje de PKG para el conversor PS2-a-PS4.
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
from typing import Optional

from .sfo_builder import SFOBuilder
from .gp4_builder import GP4Builder, create_ps2_classic_gp4
from .config_generator import EmulatorConfig, get_game_config, detect_game_id
from .iso_utils import validate_ps2_iso, get_iso_info, convert_bin_to_iso

logger = logging.getLogger(__name__)

_CUSA_RANGE_MIN = 90000
_CUSA_RANGE_MAX = 99999
_ICON_SIZE = 512
_PLACEHOLDER_BG_COLOR = (0x1A, 0x23, 0x7E)
_PLACEHOLDER_TEXT_COLOR = (0xFF, 0xFF, 0xFF)

# Keystone estándar de 64 bytes para fPKG (passcode 0000...0000)
_DEFAULT_KEYSTONE = bytes.fromhex(
    "6b657973746f6e650200010000000000"
    "00000000000000000000000000000000"
    "24326124313024584f397a56386b324d"
    "6e507152735475567758795a30313233"
)


def _create_placeholder_icon_pure(output_path: str, width: int = _ICON_SIZE, height: int = _ICON_SIZE, bg_color: tuple = _PLACEHOLDER_BG_COLOR) -> None:
    def _make_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk_body = chunk_type + data
        return struct.pack(">I", len(data)) + chunk_body + struct.pack(">I", zlib.crc32(chunk_body) & 0xFFFFFFFF)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_chunk = _make_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    r, g, b = bg_color
    row = b"\x00" + bytes([r, g, b]) * width
    idat_chunk = _make_chunk(b"IDAT", zlib.compress(row * height))
    iend_chunk = _make_chunk(b"IEND", b"")
    with open(output_path, "wb") as f:
        f.write(signature + ihdr_chunk + idat_chunk + iend_chunk)


def create_placeholder_icon(output_path: str, title: str) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (_ICON_SIZE, _ICON_SIZE), _PLACEHOLDER_BG_COLOR)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 36)
        except Exception:
            font = ImageFont.load_default()
        draw.text((140, 180), "PS2 Classic", fill=(0x80, 0x80, 0xFF), font=font)
        draw.text((60, 250), (title or "PS2 Game")[:22], fill=_PLACEHOLDER_TEXT_COLOR, font=font)
        img.save(output_path, "PNG")
    except ImportError:
        _create_placeholder_icon_pure(output_path)


def _prepare_image_asset(src_path: str, dest_path: str, target_size: tuple[int, int]) -> None:
    """Convierte y redimensiona imágenes a PNG RGB 24-bit exacto si Pillow está instalado."""
    try:
        from PIL import Image
        with Image.open(src_path) as img:
            rgb_img = img.convert("RGB")
            if rgb_img.size != target_size:
                rgb_img = rgb_img.resize(target_size, Image.Resampling.LANCZOS)
            rgb_img.save(dest_path, "PNG")
    except ImportError:
        shutil.copy2(src_path, dest_path)


class PKGProject:
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
        emu_config: Optional[EmulatorConfig] = None,
        game_config: Optional[dict] = None,
        icon_path: Optional[str] = None,
        pic_path: Optional[str] = None,
        progress_callback: Optional[object] = None,
        **kwargs,
    ) -> None:
        resolved_name = project_name or game_title or (
            os.path.splitext(os.path.basename(iso_paths[0]))[0] if iso_paths else "PS2_Game"
        )
        clean_name = "".join(c for c in resolved_name if c.isalnum() or c in (" ", "_", "-")).strip()
        self._project_name: str = clean_name or "PS2_Game"
        self._output_dir: str = output_dir or os.path.abspath("output")

        self.title: str = game_title or ""
        self.title_id: str = title_id or ""
        self.content_id: str = content_id or ""
        self.ps2_game_id: str = game_id or ""

        self.iso_paths: list[str] = list(iso_paths) if iso_paths else []
        self.icon_path: Optional[str] = icon_path
        self.bg_path: Optional[str] = pic_path or kwargs.get("bg_path")
        self.startup_image_path: Optional[str] = kwargs.get("startup_image_path")
        self.eboot_path: Optional[str] = eboot_path
        self.emulator_config: Optional[EmulatorConfig] = emu_config
        self.progress_callback = progress_callback

    @property
    def project_dir(self) -> str:
        return os.path.abspath(os.path.join(self._output_dir, self._project_name))

    @property
    def assets_dir(self) -> str:
        if self.eboot_path:
            return os.path.dirname(os.path.abspath(self.eboot_path))
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets"))

    def generate_title_id(self) -> str:
        if self.ps2_game_id:
            hash_digest = hashlib.md5(self.ps2_game_id.encode("utf-8")).hexdigest()
            hash_int = int(hash_digest[:8], 16)
            cusa_num = _CUSA_RANGE_MIN + (hash_int % (_CUSA_RANGE_MAX - _CUSA_RANGE_MIN + 1))
        else:
            cusa_num = random.randint(_CUSA_RANGE_MIN, _CUSA_RANGE_MAX)
        return f"CUSA{cusa_num:05d}"

    def generate_content_id(self) -> str:
        if not self.title_id:
            self.title_id = self.generate_title_id()
        cleaned = "".join(c for c in (self.ps2_game_id or "").upper() if c.isalnum())
        game_part = (cleaned[:12].ljust(12, "0") + "0001")[:16]
        return f"UP9000-{self.title_id}_00-{game_part}"

    def auto_detect(self) -> None:
        if not self.iso_paths:
            raise ValueError("No se han proporcionado rutas de ISO.")
        first_iso = self.iso_paths[0]

        detected_id = detect_game_id(first_iso)
        if detected_id:
            self.ps2_game_id = detected_id

        iso_info = get_iso_info(first_iso)
        if iso_info:
            if not self.title and iso_info.get("title"):
                self.title = iso_info["title"]
            if not self.ps2_game_id and iso_info.get("game_id"):
                self.ps2_game_id = iso_info["game_id"]

        if not self.title:
            iso_basename = os.path.splitext(os.path.basename(first_iso))[0]
            self.title = iso_basename.replace("_", " ").replace(".", " ").strip()

        if not self.title_id:
            self.title_id = self.generate_title_id()
        if not self.content_id:
            self.content_id = self.generate_content_id()

        if self.emulator_config is None:
            self.emulator_config = EmulatorConfig(
                ps2_title_id=self.ps2_game_id or "SLUS-20946",
                num_discs=len(self.iso_paths),
            )
            self.emulator_config.apply_compatibility_patches(self.ps2_game_id)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.title:
            errors.append("El título del juego (title) es obligatorio.")
        if not self.title_id or not self.title_id.startswith("CUSA") or len(self.title_id) != 9:
            errors.append(f"title_id '{self.title_id}' inválido (se espera CUSAxxxxx).")
        if not self.content_id or len(self.content_id) != 36:
            errors.append(f"content_id '{self.content_id}' debe tener 36 caracteres.")

        if not self.iso_paths:
            errors.append("Se requiere al menos una ruta de ISO.")
        else:
            for i, iso_path in enumerate(self.iso_paths):
                if not os.path.isfile(iso_path):
                    errors.append(f"Archivo ISO #{i + 1} no encontrado: '{iso_path}'")
                elif not iso_path.lower().endswith((".bin", ".img")):
                    val_res = validate_ps2_iso(iso_path)
                    if not val_res.get("valid", False):
                        errors.append(f"ISO #{i + 1} inválida: {', '.join(val_res.get('errors', []))}")

        if self.eboot_path and not os.path.isfile(self.eboot_path):
            errors.append(f"eboot.bin no encontrado: '{self.eboot_path}'")
        return errors

    def build_project(self) -> str:
        errors = self.validate()
        if errors:
            raise ValueError("Errores de validación:\n" + "\n".join(f"  - {e}" for e in errors))

        proj_dir = self.project_dir
        sce_sys_dir = os.path.join(proj_dir, "sce_sys")
        image_dir = os.path.join(proj_dir, "image")
        patches_dir = os.path.join(proj_dir, "patches")

        os.makedirs(sce_sys_dir, exist_ok=True)
        os.makedirs(image_dir, exist_ok=True)
        os.makedirs(patches_dir, exist_ok=True)

        # 1. Copiar archivos base de la plantilla del emulador desde assets/
        self._copy_emulator_template_files(proj_dir, sce_sys_dir)

        # 2. PARAM.SFO y keystone
        self._build_sfo(os.path.join(sce_sys_dir, "param.sfo"))
        keystone_path = os.path.join(sce_sys_dir, "keystone")
        if not os.path.isfile(keystone_path):
            with open(keystone_path, "wb") as kf:
                kf.write(_DEFAULT_KEYSTONE)

        # 3. Icono y fondos redimensionados a formato PS4
        self._build_icon(os.path.join(sce_sys_dir, "icon0.png"))
        if self.bg_path and os.path.isfile(self.bg_path):
            _prepare_image_asset(self.bg_path, os.path.join(sce_sys_dir, "pic0.png"), (1920, 1080))
        if self.startup_image_path and os.path.isfile(self.startup_image_path):
            _prepare_image_asset(self.startup_image_path, os.path.join(sce_sys_dir, "pic1.png"), (1920, 1080))

        # 4. ISOs de disco (con conversión automática si es .bin)
        self._build_disc_images(image_dir)

        # 5. Configuración del emulador y parches Lua
        self._build_emulator_config(os.path.join(proj_dir, "config-emu-ps4.txt"), patches_dir)

        # 6. eboot.bin
        self._build_eboot(os.path.join(proj_dir, "eboot.bin"))

        # 7. Archivo GP4
        gp4_path = os.path.join(proj_dir, f"{self._project_name}.gp4")
        self._build_gp4(gp4_path, proj_dir)

        return proj_dir

    def _copy_emulator_template_files(self, proj_dir: str, sce_sys_dir: str) -> None:
        """Copia los módulos obligatorios del emulador PS2 desde assets/ si están presentes."""
        assets = self.assets_dir
        if not os.path.isdir(assets):
            return

        # Archivos raíz del emulador (ps2-emu-compiler.self, formatted.card, *.crack, etc.)
        for fname in os.listdir(assets):
            src = os.path.join(assets, fname)
            if os.path.isfile(src) and (
                fname in ("ps2-emu-compiler.self", "formatted.card", "sce-discmap.plt")
                or fname.endswith(".crack")
            ):
                shutil.copy2(src, os.path.join(proj_dir, fname))
                logger.info("Archivo base del emulador copiado: %s", fname)

        # Subcarpetas del emulador (sce_module, lua_include, feature_data, trophy_data, sce_sys)
        for subdir in ("sce_module", "lua_include", "feature_data", "trophy_data", "sce_sys"):
            src_sub = os.path.join(assets, subdir)
            if os.path.isdir(src_sub):
                dst_sub = os.path.join(proj_dir, subdir)
                shutil.copytree(src_sub, dst_sub, dirs_exist_ok=True)
                logger.info("Carpeta base del emulador copiada: %s/", subdir)

        # Advertir si faltan archivos críticos para que el juego arranque en PS4
        critical_checks = [
            os.path.join(proj_dir, "sce_module", "libc.prx"),
            os.path.join(proj_dir, "sce_module", "libSceFios2.prx"),
            os.path.join(proj_dir, "ps2-emu-compiler.self"),
        ]
        missing = [os.path.relpath(p, proj_dir) for p in critical_checks if not os.path.isfile(p)]
        if missing:
            logger.warning(
                "ATENCIÓN: Faltan archivos base del emulador en assets/ (%s). "
                "Sin ellos, la PS4 mostrará 'Los datos de la aplicación están dañados' al iniciar.",
                ", ".join(missing),
            )

    def _build_sfo(self, sfo_path: str) -> None:
        builder = SFOBuilder()
        builder.set_title(self.title)
        builder.set_title_id(self.title_id)
        builder.set_content_id(self.content_id)
        builder.save(sfo_path)

    def _build_icon(self, icon_dest: str) -> None:
        if self.icon_path and os.path.isfile(self.icon_path):
            _prepare_image_asset(self.icon_path, icon_dest, (_ICON_SIZE, _ICON_SIZE))
        else:
            create_placeholder_icon(icon_dest, self.title)

    def _build_disc_images(self, image_dir: str) -> None:
        for idx, iso_path in enumerate(self.iso_paths, start=1):
            disc_name = f"disc{idx:02d}.iso"
            dest = os.path.join(image_dir, disc_name)
            iso_abs = os.path.abspath(iso_path)

            if iso_abs.lower().endswith((".bin", ".img")):
                logger.info("Convirtiendo imagen RAW (%s) a ISO9660...", os.path.basename(iso_abs))
                convert_bin_to_iso(iso_abs, dest)
                continue

            shutil.copy2(iso_abs, dest)
            logger.info("ISO copiada: %s -> %s", iso_abs, dest)

    def _build_emulator_config(self, config_path: str, patches_dir: str) -> None:
        if self.emulator_config is None:
            self.emulator_config = EmulatorConfig(
                ps2_title_id=self.ps2_game_id or "SLUS-20946",
                num_discs=len(self.iso_paths),
            )
            self.emulator_config.apply_compatibility_patches(self.ps2_game_id)

        self.emulator_config.num_discs = len(self.iso_paths)
        self.emulator_config.to_file(config_path)

        # Escribir script Lua si existen parches
        if hasattr(self.emulator_config, "generate_lua_script"):
            lua_script = self.emulator_config.generate_lua_script()
            if lua_script:
                lua_filename = f"{self.emulator_config.ps2_title_id}_config.lua"
                lua_path = os.path.join(patches_dir, lua_filename)
                with open(lua_path, "w", encoding="utf-8", newline="\n") as lf:
                    lf.write(lua_script)
                logger.info("Parche Lua generado en: %s", lua_path)

    def _build_eboot(self, eboot_dest: str) -> None:
        if self.eboot_path and os.path.isfile(self.eboot_path):
            shutil.copy2(self.eboot_path, eboot_dest)

    def _build_gp4(self, gp4_path: str, proj_dir: str) -> None:
        create_ps2_classic_gp4(
            content_id=self.content_id,
            project_dir=proj_dir,
            iso_paths=[
                os.path.join(proj_dir, "image", f"disc{i:02d}.iso")
                for i in range(1, len(self.iso_paths) + 1)
            ],
            output_path=gp4_path,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def build_pkg(self, orbis_pub_cmd_path: Optional[str] = None) -> Optional[str]:
        cmd_path = self._find_orbis_pub_cmd(orbis_pub_cmd_path)
        if cmd_path is None:
            logger.warning("orbis-pub-cmd.exe no encontrado. Use el archivo GP4 en: %s", self.project_dir)
            return None

        gp4_file = os.path.join(self.project_dir, f"{self._project_name}.gp4")
        pkg_output_dir = os.path.join(self._output_dir, "pkg")
        os.makedirs(pkg_output_dir, exist_ok=True)
        pkg_output = os.path.join(pkg_output_dir, f"{self.content_id}.pkg")

        cmd_args = [cmd_path, "img_create", "--oformat", "pkg", gp4_file, pkg_output]
        logger.info("Ejecutando: %s", " ".join(cmd_args))

        result = subprocess.run(cmd_args, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            raise RuntimeError(f"orbis-pub-cmd falló ({result.returncode}):\n{result.stderr.strip() or result.stdout.strip()}")

        logger.info("PKG generado exitosamente: %s", pkg_output)
        return pkg_output

    def build(self) -> str:
        proj_dir = self.build_project()
        if self.progress_callback:
            self.progress_callback(65)
        pkg_path = self.build_pkg()
        return pkg_path or proj_dir

    def _find_orbis_pub_cmd(self, explicit_path: Optional[str] = None) -> Optional[str]:
        exe_name = "orbis-pub-cmd.exe"
        if explicit_path and os.path.isfile(explicit_path):
            return os.path.abspath(explicit_path)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        for c in (
            os.path.join(script_dir, exe_name),
            os.path.join(script_dir, "..", exe_name),
            os.path.join(script_dir, "..", "assets", exe_name),
            os.path.join(self.project_dir, exe_name),
        ):
            if os.path.isfile(c):
                return os.path.abspath(c)
        found = shutil.which(exe_name)
        return os.path.abspath(found) if found else None


def quick_convert(iso_path: str, output_dir: str, eboot_path: Optional[str] = None, **kwargs) -> str:
    if not os.path.isfile(iso_path):
        raise FileNotFoundError(f"Archivo ISO no encontrado: '{iso_path}'")
    iso_basename = os.path.splitext(os.path.basename(iso_path))[0]
    project_name = kwargs.pop("project_name", iso_basename)

    project = PKGProject(project_name, output_dir, iso_paths=[iso_path], eboot_path=eboot_path)
    project.auto_detect()

    for key in ("title", "title_id", "content_id", "ps2_game_id", "icon_path", "bg_path", "startup_image_path"):
        if key in kwargs and kwargs[key] is not None:
            setattr(project, key, kwargs[key])

    if "title_id" in kwargs and "content_id" not in kwargs:
        project.content_id = project.generate_content_id()

    return project.build()