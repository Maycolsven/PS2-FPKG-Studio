"""
gp4_builder.py - Generador de archivos .gp4 (XML de proyecto) para orbis-pub-cmd.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_DEFAULT_PASSCODE = "00000000000000000000000000000000"
_DEFAULT_TIMESTAMP = "2024-01-01 00:00:00"
_VOLUME_TYPE = "pkg_ps4_app"
_VOLUME_ID = "PS4VOLUME"
_STORAGE_TYPE = "digital50"
_APP_TYPE = "full"


@dataclass
class _FileEntry:
    source_path: str
    target_path: str


@dataclass
class _DirNode:
    name: str
    subdirs: Dict[str, "_DirNode"] = field(default_factory=dict)
    files: List[tuple] = field(default_factory=list)


class GP4Builder:
    def __init__(self, content_id: str, passcode: str = _DEFAULT_PASSCODE) -> None:
        self._validate_content_id(content_id)
        self._validate_passcode(passcode)
        self._content_id: str = content_id
        self._passcode: str = passcode
        self._timestamp: str = _DEFAULT_TIMESTAMP
        self._files: List[_FileEntry] = []

    def set_volume_timestamp(self, timestamp: str) -> None:
        parts = timestamp.strip().split(" ")
        if len(parts) != 2 or len(parts[0].split("-")) != 3 or len(parts[1].split(":")) != 3:
            raise ValueError(f"Formato de timestamp inválido: '{timestamp}'.")
        self._timestamp = timestamp.strip()

    def add_file(self, source_path: str, target_path: str) -> None:
        target_normalized = target_path.replace("\\", "/").strip("/")
        if not target_normalized:
            raise ValueError("target_path no puede estar vacío.")
        source_normalized = source_path.replace("\\", "/")
        if not any(f.target_path == target_normalized for f in self._files):
            self._files.append(_FileEntry(source_path=source_normalized, target_path=target_normalized))

    def build_xml(self) -> str:
        root = self._build_element_tree()
        return self._serialize_tree(root)

    def save(self, output_path: str) -> None:
        gp4_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(gp4_dir, exist_ok=True)
        root = self._build_element_tree(gp4_dir=gp4_dir)
        xml_str = self._serialize_tree(root)
        with open(output_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(xml_str)

    def _build_element_tree(self, gp4_dir: Optional[str] = None) -> ET.Element:
        psproject = ET.Element("psproject")
        psproject.set("fmt", "gp4")
        psproject.set("version", "1000")

        volume = ET.SubElement(psproject, "volume")
        ET.SubElement(volume, "volume_type").text = _VOLUME_TYPE
        ET.SubElement(volume, "volume_id").text = _VOLUME_ID
        ET.SubElement(volume, "volume_ts").text = self._timestamp

        package = ET.SubElement(volume, "package")
        package.set("content_id", self._content_id)
        package.set("passcode", self._passcode)
        package.set("storage_type", _STORAGE_TYPE)
        package.set("app_type", _APP_TYPE)

        self._build_chunk_info(volume)

        files_elem = ET.SubElement(psproject, "files")
        files_elem.set("img_no", "0")
        self._build_files_section(files_elem, gp4_dir)

        rootdir_elem = ET.SubElement(psproject, "rootdir")
        self._build_rootdir_section(rootdir_elem, gp4_dir)

        return psproject

    def _build_chunk_info(self, parent: ET.Element) -> None:
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

    def _build_files_section(self, parent: ET.Element, gp4_dir: Optional[str]) -> None:
        for entry in self._files:
            file_elem = ET.SubElement(parent, "file")
            file_elem.set("targ_path", entry.target_path)
            file_elem.set("orig_path", self._compute_orig_path(entry, gp4_dir))

    def _build_rootdir_section(self, parent: ET.Element, gp4_dir: Optional[str]) -> None:
        tree_root = _DirNode(name="")
        for entry in self._files:
            parts = entry.target_path.split("/")
            current = tree_root
            for dir_part in parts[:-1]:
                if dir_part not in current.subdirs:
                    current.subdirs[dir_part] = _DirNode(name=dir_part)
                current = current.subdirs[dir_part]
            filename = parts[-1]
            orig = self._compute_orig_path(entry, gp4_dir)
            current.files.append((filename, orig))
        self._serialize_dir_node(tree_root, parent)

    def _serialize_dir_node(self, node: _DirNode, parent: ET.Element) -> None:
        for dir_name in sorted(node.subdirs.keys()):
            child_node = node.subdirs[dir_name]
            dir_elem = ET.SubElement(parent, "dir")
            dir_elem.set("targ_name", dir_name)
            self._serialize_dir_node(child_node, dir_elem)

    def _compute_orig_path(self, entry: _FileEntry, gp4_dir: Optional[str]) -> str:
        if gp4_dir is None:
            return entry.source_path
        source_abs = os.path.abspath(entry.source_path)
        try:
            rel = os.path.relpath(source_abs, gp4_dir)
        except ValueError:
            rel = source_abs
        return rel.replace("\\", "/")

    @staticmethod
    def _serialize_tree(root: ET.Element) -> str:
        ET.indent(root, space="  ")
        xml_bytes = ET.tostring(root, encoding="unicode", xml_declaration=False)
        declaration = '<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n'
        return declaration + xml_bytes + "\n"

    @staticmethod
    def _validate_content_id(content_id: str) -> None:
        if not content_id or len(content_id) != 36:
            raise ValueError(f"content_id debe tener 36 caracteres: '{content_id}'")

    @staticmethod
    def _validate_passcode(passcode: str) -> None:
        if not passcode or len(passcode) != 32:
            raise ValueError("passcode debe tener 32 caracteres.")
        int(passcode, 16)


def create_ps2_classic_gp4(
    content_id: str,
    project_dir: str,
    iso_paths: List[str],
    output_path: str,
    passcode: str = _DEFAULT_PASSCODE,
    timestamp: Optional[str] = None,
) -> str:
    """Escanea recursivamente todo project_dir (incluyendo sce_module, patches, lua_include, sce_sys)."""
    project_dir = os.path.abspath(project_dir)
    if not os.path.isdir(project_dir):
        raise FileNotFoundError(f"El directorio del proyecto no existe: '{project_dir}'")
    if not iso_paths:
        raise ValueError("Se requiere al menos una ISO de PS2 en iso_paths.")

    builder = GP4Builder(content_id, passcode)
    if timestamp:
        builder.set_volume_timestamp(timestamp)

    # Escanear recursivamente todos los archivos del proyecto excepto .gp4 y la carpeta image/
    for dirpath, _dirnames, filenames in os.walk(project_dir):
        for fname in sorted(filenames):
            if fname.endswith(".gp4"):
                continue
            full_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(full_path, project_dir).replace("\\", "/")
            if rel_path.startswith("image/"):
                continue
            builder.add_file(full_path, rel_path)

    # Agregar ISOs de disco en image/discXX.iso
    for idx, iso_path in enumerate(iso_paths, start=1):
        iso_abs = os.path.abspath(iso_path)
        if not os.path.isfile(iso_abs):
            raise FileNotFoundError(f"Archivo ISO no encontrado: '{iso_path}'")
        builder.add_file(iso_abs, f"image/disc{idx:02d}.iso")

    abs_output = os.path.abspath(output_path)
    builder.save(abs_output)
    return abs_output