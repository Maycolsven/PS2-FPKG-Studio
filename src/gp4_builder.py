"""
gp4_builder.py - Generador de archivos .gp4 (XML de proyecto) para orbis-pub-cmd.

Este módulo construye los archivos de proyecto GP4 que orbis-pub-cmd utiliza
para empaquetar contenido en archivos .pkg de PS4. Está diseñado específicamente
para el flujo de conversión PS2-a-PS4 (PS2 Classics).

Estructura del GP4:
    psproject
    └── volume
        ├── volume_type, volume_id, volume_ts
        ├── package (content_id, passcode, storage_type, app_type)
        ├── chunk_info (chunks + scenarios)
        ├── files (lista plana de archivos con orig_path / targ_path)
        └── rootdir (árbol jerárquico de directorios y archivos)
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Constantes por defecto
# ---------------------------------------------------------------------------

_DEFAULT_PASSCODE = "00000000000000000000000000000000"
_DEFAULT_TIMESTAMP = "2024-01-01 00:00:00"
_VOLUME_TYPE = "pkg_ps4_app"
_VOLUME_ID = "PS4VOLUME"
_STORAGE_TYPE = "digital50"
_APP_TYPE = "full"

# Archivos estándar que se buscan en un proyecto PS2 Classics
_PS2_CLASSIC_STANDARD_FILES = [
    "sce_sys/param.sfo",
    "sce_sys/icon0.png",
    "sce_sys/pic1.png",
    "sce_sys/trophy/trophy00.trp",
    "eboot.bin",
    "sce_sys/about/right.sprx",
    "config-emu-ps4.txt",
    "sce_sys/pic0.png",
    "sce_sys/keystone",
]


# ---------------------------------------------------------------------------
# Estructuras internas
# ---------------------------------------------------------------------------

@dataclass
class _FileEntry:
    """Representa un archivo mapeado: ruta real en disco → ruta destino en el PKG."""

    source_path: str  # Ruta absoluta o relativa en el sistema de archivos real
    target_path: str  # Ruta dentro del PKG (ej: "sce_sys/param.sfo")


@dataclass
class _DirNode:
    """Nodo de un árbol de directorios para construir la sección <rootdir>."""

    name: str
    subdirs: Dict[str, "_DirNode"] = field(default_factory=dict)
    files: List[tuple] = field(default_factory=list)  # (filename, orig_path)


# ---------------------------------------------------------------------------
# Clase principal
# ---------------------------------------------------------------------------

class GP4Builder:
    """Construye un archivo de proyecto GP4 para orbis-pub-cmd.

    Uso básico::

        builder = GP4Builder("UP9000-CUSA00001_00-PS2GAMECLASSIC01")
        builder.add_file("build/sce_sys/param.sfo", "sce_sys/param.sfo")
        builder.add_file("build/eboot.bin", "eboot.bin")
        builder.set_volume_timestamp("2024-06-15 12:00:00")
        builder.save("output/project.gp4")

    Args:
        content_id: Identificador de contenido PS4 (36 caracteres).
                    Formato: ``XX9999-CUSAXXXXX_00-XXXXXXXXXXXXXXXX``
        passcode: Clave de 32 caracteres hexadecimales para el paquete.
    """

    def __init__(
        self,
        content_id: str,
        passcode: str = _DEFAULT_PASSCODE,
    ) -> None:
        self._validate_content_id(content_id)
        self._validate_passcode(passcode)

        self._content_id: str = content_id
        self._passcode: str = passcode
        self._timestamp: str = _DEFAULT_TIMESTAMP
        self._files: List[_FileEntry] = []

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def set_volume_timestamp(self, timestamp: str) -> None:
        """Establece la marca de tiempo del volumen.

        Args:
            timestamp: Fecha/hora en formato ``"YYYY-MM-DD HH:MM:SS"``.

        Raises:
            ValueError: Si el formato es inválido.
        """
        # Validación básica del formato
        parts = timestamp.strip().split(" ")
        if len(parts) != 2:
            raise ValueError(
                f"Formato de timestamp inválido: '{timestamp}'. "
                "Se espera 'YYYY-MM-DD HH:MM:SS'."
            )
        date_parts = parts[0].split("-")
        time_parts = parts[1].split(":")
        if len(date_parts) != 3 or len(time_parts) != 3:
            raise ValueError(
                f"Formato de timestamp inválido: '{timestamp}'. "
                "Se espera 'YYYY-MM-DD HH:MM:SS'."
            )
        self._timestamp = timestamp.strip()

    def add_file(self, source_path: str, target_path: str) -> None:
        """Agrega un archivo al proyecto GP4.

        Args:
            source_path: Ruta real del archivo en el sistema de archivos.
            target_path: Ruta de destino dentro del PKG (ej: ``"sce_sys/param.sfo"``).
                         Se normaliza a barras inclinadas hacia adelante.

        Raises:
            ValueError: Si ``target_path`` está vacío.
        """
        # Normalizar separadores a forward-slash (formato PKG)
        target_normalized = target_path.replace("\\", "/").strip("/")
        if not target_normalized:
            raise ValueError("target_path no puede estar vacío.")

        source_normalized = source_path.replace("\\", "/")

        self._files.append(_FileEntry(
            source_path=source_normalized,
            target_path=target_normalized,
        ))

    def build_xml(self) -> str:
        """Genera el contenido XML del archivo GP4.

        Returns:
            Cadena XML completa con declaración, lista para escribir en disco.
        """
        root = self._build_element_tree()
        return self._serialize_tree(root)

    def save(self, output_path: str) -> None:
        """Genera y escribe el archivo GP4 en disco.

        Las rutas ``orig_path`` de cada archivo se convierten a rutas
        relativas respecto al directorio donde se guarda el GP4.

        Args:
            output_path: Ruta del archivo .gp4 a crear.
        """
        gp4_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(gp4_dir, exist_ok=True)

        root = self._build_element_tree(gp4_dir=gp4_dir)
        xml_str = self._serialize_tree(root)

        with open(output_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(xml_str)

    # ------------------------------------------------------------------
    # Construcción del árbol XML
    # ------------------------------------------------------------------

    def _build_element_tree(self, gp4_dir: Optional[str] = None) -> ET.Element:
        """Construye el árbol de elementos XML completo.

        Args:
            gp4_dir: Directorio base del GP4 para calcular rutas relativas.
                     Si es ``None``, se usan las rutas tal cual.

        Returns:
            Elemento raíz ``<psproject>``.
        """
        # Raíz
        psproject = ET.Element("psproject")
        psproject.set("fmt", "gp4")
        psproject.set("version", "1000")

        # Volume
        volume = ET.SubElement(psproject, "volume")

        ET.SubElement(volume, "volume_type").text = _VOLUME_TYPE
        ET.SubElement(volume, "volume_id").text = _VOLUME_ID
        ET.SubElement(volume, "volume_ts").text = self._timestamp

        # Package
        package = ET.SubElement(volume, "package")
        package.set("content_id", self._content_id)
        package.set("passcode", self._passcode)
        package.set("storage_type", _STORAGE_TYPE)
        package.set("app_type", _APP_TYPE)

        # Chunk info
        self._build_chunk_info(volume)

        # Files (lista plana) - hijo directo de psproject
        files_elem = ET.SubElement(psproject, "files")
        files_elem.set("img_no", "0")
        self._build_files_section(files_elem, gp4_dir)

        # Rootdir (árbol jerárquico) - hijo directo de psproject
        rootdir_elem = ET.SubElement(psproject, "rootdir")
        self._build_rootdir_section(rootdir_elem, gp4_dir)

        return psproject

    def _build_chunk_info(self, parent: ET.Element) -> None:
        """Agrega la sección ``<chunk_info>`` con un chunk y un escenario por defecto."""
        chunk_info = ET.SubElement(parent, "chunk_info")
        chunk_info.set("chunk_count", "1")
        chunk_info.set("scenario_count", "1")

        chunks = ET.SubElement(chunk_info, "chunks")
        chunk = ET.SubElement(chunks, "chunk")
        chunk.set("id", "0")
        chunk.set("layer_no", "0")
        chunk.set("label", "Chunk #0")

        scenarios = ET.SubElement(chunk_info, "scenarios")
        scenarios.set("default_id", "0")

        scenario = ET.SubElement(scenarios, "scenario")
        scenario.set("id", "0")
        scenario.set("type", "sp")
        scenario.set("initial_chunk_count", "1")
        scenario.set("label", "Scenario #0")
        scenario.text = "0"

    def _build_files_section(
        self, parent: ET.Element, gp4_dir: Optional[str]
    ) -> None:
        """Agrega entradas ``<file>`` planas a la sección ``<files>``.

        Cada entrada tiene ``targ_path`` (ruta destino en PKG) y
        ``orig_path`` (ruta relativa al GP4).
        """
        for entry in self._files:
            file_elem = ET.SubElement(parent, "file")
            file_elem.set("targ_path", entry.target_path)
            file_elem.set("orig_path", self._compute_orig_path(entry, gp4_dir))

    def _build_rootdir_section(
        self, parent: ET.Element, gp4_dir: Optional[str]
    ) -> None:
        """Construye el árbol jerárquico ``<rootdir>`` con ``<dir>`` y ``<file>``."""
        # Primero construimos un árbol lógico a partir de los target_paths
        tree_root = _DirNode(name="")

        for entry in self._files:
            parts = entry.target_path.split("/")
            current = tree_root

            # Navegar/crear subdirectorios
            for dir_part in parts[:-1]:
                if dir_part not in current.subdirs:
                    current.subdirs[dir_part] = _DirNode(name=dir_part)
                current = current.subdirs[dir_part]

            # Agregar el archivo al nodo actual
            filename = parts[-1]
            orig = self._compute_orig_path(entry, gp4_dir)
            current.files.append((filename, orig))

        # Serializar el árbol al XML
        self._serialize_dir_node(tree_root, parent)

    def _serialize_dir_node(self, node: _DirNode, parent: ET.Element) -> None:
        """Serializa recursivamente un ``_DirNode`` como elementos XML (solo <dir>)."""
        # Subdirectorios (orden alfabético para determinismo)
        for dir_name in sorted(node.subdirs.keys()):
            child_node = node.subdirs[dir_name]
            dir_elem = ET.SubElement(parent, "dir")
            dir_elem.set("targ_name", dir_name)
            self._serialize_dir_node(child_node, dir_elem)

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------

    def _compute_orig_path(
        self, entry: _FileEntry, gp4_dir: Optional[str]
    ) -> str:
        """Calcula la ruta relativa de ``orig_path`` respecto al directorio GP4.

        Si ``gp4_dir`` es ``None``, devuelve la ruta fuente tal cual.
        Si la ruta fuente es relativa y ``gp4_dir`` es provisto, se resuelve
        contra el directorio actual antes de relativizar.
        """
        if gp4_dir is None:
            return entry.source_path

        source_abs = os.path.abspath(entry.source_path)
        try:
            rel = os.path.relpath(source_abs, gp4_dir)
        except ValueError:
            # En Windows, relpath falla si están en unidades distintas
            rel = source_abs

        # Normalizar a forward-slash
        return rel.replace("\\", "/")

    @staticmethod
    def _serialize_tree(root: ET.Element) -> str:
        """Serializa el árbol XML a una cadena con formato legible.

        Returns:
            Cadena XML con declaración ``<?xml ...?>`` e indentación.
        """
        ET.indent(root, space="  ")
        xml_bytes = ET.tostring(root, encoding="unicode", xml_declaration=False)
        declaration = '<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n'
        return declaration + xml_bytes + "\n"

    @staticmethod
    def _validate_content_id(content_id: str) -> None:
        """Valida el formato del content_id.

        Formato esperado: ``XX9999-CUSAXXXXX_00-XXXXXXXXXXXXXXXX`` (36 chars).

        Raises:
            ValueError: Si la longitud o el formato son incorrectos.
        """
        if not content_id or len(content_id) != 36:
            raise ValueError(
                f"content_id debe tener 36 caracteres, se recibieron "
                f"{len(content_id) if content_id else 0}: '{content_id}'"
            )
        # Los guiones estándar en Content ID de PS4 están en las posiciones 6 y 19
        # Ej: UP9000-CUSA00622_00-SLES549520000000
        if len(content_id) == 36 and (content_id[6] != "-" or content_id[19] != "-"):
            # Permitir si tiene longitud 36 para compatibilidad con homebrew
            pass

    @staticmethod
    def _validate_passcode(passcode: str) -> None:
        """Valida el passcode (32 caracteres hexadecimales).

        Raises:
            ValueError: Si la longitud o los caracteres son incorrectos.
        """
        if not passcode or len(passcode) != 32:
            raise ValueError(
                f"passcode debe tener 32 caracteres, se recibieron "
                f"{len(passcode) if passcode else 0}."
            )
        # Verificar que sean todos caracteres hexadecimales
        try:
            int(passcode, 16)
        except ValueError:
            raise ValueError(
                f"passcode debe contener solo caracteres hexadecimales: '{passcode}'."
            )


# ---------------------------------------------------------------------------
# Función de conveniencia para PS2 Classics
# ---------------------------------------------------------------------------

def create_ps2_classic_gp4(
    content_id: str,
    project_dir: str,
    iso_paths: List[str],
    output_path: str,
    passcode: str = _DEFAULT_PASSCODE,
    timestamp: Optional[str] = None,
) -> str:
    """Genera un archivo GP4 completo para un proyecto PS2 Classics.

    Escanea ``project_dir`` en busca de los archivos estándar de PS2 Classics
    (param.sfo, icon0.png, eboot.bin, etc.) y agrega las ISOs de disco
    como ``image/disc01.iso``, ``image/disc02.iso``, etc.

    Args:
        content_id: Identificador de contenido PS4 (36 caracteres).
        project_dir: Directorio raíz del proyecto con los archivos del PKG.
        iso_paths: Lista de rutas a archivos ISO de PS2.
                   Se numeran secuencialmente como disc01, disc02, etc.
        output_path: Ruta de salida para el archivo .gp4.
        passcode: Clave de 32 caracteres hexadecimales (por defecto todo ceros).
        timestamp: Marca de tiempo opcional en formato ``"YYYY-MM-DD HH:MM:SS"``.

    Returns:
        Ruta absoluta del archivo GP4 generado.

    Raises:
        FileNotFoundError: Si ``project_dir`` no existe o no se encuentra
                           ningún archivo estándar ni ISOs.
        ValueError: Si ``iso_paths`` está vacío.
    """
    project_dir = os.path.abspath(project_dir)

    if not os.path.isdir(project_dir):
        raise FileNotFoundError(
            f"El directorio del proyecto no existe: '{project_dir}'"
        )

    if not iso_paths:
        raise ValueError("Se requiere al menos una ISO de PS2 en iso_paths.")

    builder = GP4Builder(content_id, passcode)

    if timestamp:
        builder.set_volume_timestamp(timestamp)

    # --- Escanear archivos estándar del proyecto ---
    files_found = 0

    for rel_path in _PS2_CLASSIC_STANDARD_FILES:
        full_path = os.path.join(project_dir, rel_path.replace("/", os.sep))
        if os.path.isfile(full_path):
            builder.add_file(full_path, rel_path)
            files_found += 1

    # Buscar archivos adicionales en sce_sys que no estén en la lista estándar
    sce_sys_dir = os.path.join(project_dir, "sce_sys")
    if os.path.isdir(sce_sys_dir):
        for dirpath, _dirnames, filenames in os.walk(sce_sys_dir):
            for fname in filenames:
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, project_dir).replace("\\", "/")
                # Evitar duplicados con los archivos estándar
                if rel not in _PS2_CLASSIC_STANDARD_FILES:
                    builder.add_file(full, rel)
                    files_found += 1

    # Buscar archivos adicionales en la raíz del proyecto (no recursivo)
    for fname in os.listdir(project_dir):
        full = os.path.join(project_dir, fname)
        if os.path.isfile(full) and fname not in ("eboot.bin",):
            # Solo agregar archivos raíz que no sean los ya conocidos
            if fname not in _PS2_CLASSIC_STANDARD_FILES and not fname.endswith(".gp4"):
                # Verificar que no sea un duplicado
                already_added = any(
                    f.target_path == fname for f in builder._files
                )
                if not already_added:
                    builder.add_file(full, fname)
                    files_found += 1

    # --- Agregar ISOs de disco ---
    for idx, iso_path in enumerate(iso_paths, start=1):
        iso_abs = os.path.abspath(iso_path)
        if not os.path.isfile(iso_abs):
            raise FileNotFoundError(
                f"Archivo ISO no encontrado: '{iso_path}'"
            )
        target = f"image/disc{idx:02d}.iso"
        builder.add_file(iso_abs, target)

    if files_found == 0 and not iso_paths:
        raise FileNotFoundError(
            f"No se encontraron archivos estándar en '{project_dir}' "
            "ni ISOs proporcionadas."
        )

    # --- Guardar ---
    abs_output = os.path.abspath(output_path)
    builder.save(abs_output)
    return abs_output
