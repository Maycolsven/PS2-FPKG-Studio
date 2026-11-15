"""
sfo_builder.py - Constructor de archivos PARAM.SFO compatibles con PS4.
"""

import struct
from datetime import datetime
from typing import Dict, List

SFO_MAGIC = b"\x00PSF"
SFO_VERSION = 0x00000101

PARAM_FMT_UTF8_SPECIAL = 0x0004  # UTF-8 sin null terminator obligatorio (ej. PUBTOOLINFO)
PARAM_FMT_UTF8 = 0x0204          # Cadena UTF-8 terminada en null
PARAM_FMT_UINT32 = 0x0404        # Entero sin signo de 32 bits (little-endian)

SFO_HEADER_SIZE = 20
SFO_INDEX_ENTRY_SIZE = 16


class SFOEntry:
    def __init__(self, key: str, fmt: int, value, max_len: int):
        self.key: str = key
        self.fmt: int = fmt
        self.value = value
        self.max_len: int = max_len

    def get_data_bytes(self):
        if self.fmt in (PARAM_FMT_UTF8, PARAM_FMT_UTF8_SPECIAL):
            encoded = self.value.encode("utf-8")
            if self.fmt == PARAM_FMT_UTF8:
                encoded += b"\x00"
            if len(encoded) > self.max_len:
                raise ValueError(
                    f"El valor de '{self.key}' ({len(encoded)} bytes) "
                    f"excede max_len ({self.max_len} bytes)"
                )
            param_len = len(encoded)
            data = encoded + b"\x00" * (self.max_len - len(encoded))
            return data, param_len
        elif self.fmt == PARAM_FMT_UINT32:
            return struct.pack("<I", int(self.value)), 4
        else:
            raise ValueError(f"Formato desconocido: 0x{self.fmt:04X}")


class SFOBuilder:
    def __init__(self):
        self._entries: Dict[str, SFOEntry] = {}
        self._init_default_entries()

    def _init_default_entries(self):
        today = datetime.now().strftime("%Y%m%d")
        pubtool = f"c_date={today},sdk_ver=04050000"

        self._add_entry("APP_TYPE",       PARAM_FMT_UINT32, 1,          4)
        self._add_entry("APP_VER",        PARAM_FMT_UTF8,   "01.00",    8)
        self._add_entry("ATTRIBUTE",      PARAM_FMT_UINT32, 0x20800002, 4)
        self._add_entry("CATEGORY",       PARAM_FMT_UTF8,   "gd",       4)
        self._add_entry("CONTENT_ID",     PARAM_FMT_UTF8,   "",         48)
        self._add_entry("FORMAT",         PARAM_FMT_UTF8,   "obs",      4)
        self._add_entry("PARENTAL_LEVEL", PARAM_FMT_UINT32, 3,          4)
        self._add_entry("PUBTOOLINFO",    PARAM_FMT_UTF8,   pubtool,    512)
        self._add_entry("SYSTEM_VER",     PARAM_FMT_UINT32, 0x04050000, 4)
        self._add_entry("TITLE",          PARAM_FMT_UTF8,   "",         128)
        self._add_entry("TITLE_ID",       PARAM_FMT_UTF8,   "",         12)
        self._add_entry("VERSION",        PARAM_FMT_UTF8,   "01.00",    8)

    def _add_entry(self, key: str, fmt: int, value, max_len: int):
        self._entries[key] = SFOEntry(key, fmt, value, max_len)

    def set_title(self, title: str):
        clean_title = title.encode("utf-8")[:127].decode("utf-8", errors="ignore")
        self._entries["TITLE"].value = clean_title

    def set_title_id(self, title_id: str):
        if len(title_id.encode("utf-8")) + 1 > 12:
            raise ValueError(f"title_id '{title_id}' excede 12 bytes")
        self._entries["TITLE_ID"].value = title_id

    def set_content_id(self, content_id: str):
        if len(content_id.encode("utf-8")) + 1 > 48:
            raise ValueError(f"content_id '{content_id}' excede 48 bytes")
        self._entries["CONTENT_ID"].value = content_id

    def _get_sorted_entries(self) -> List[SFOEntry]:
        return [self._entries[k] for k in sorted(self._entries.keys())]

    def build(self) -> bytes:
        entries = self._get_sorted_entries()
        num_entries = len(entries)

        key_table = bytearray()
        key_offsets: List[int] = []
        for entry in entries:
            key_offsets.append(len(key_table))
            key_table.extend(entry.key.encode("utf-8") + b"\x00")

        padding_needed = (4 - (len(key_table) % 4)) % 4
        key_table_padded = bytes(key_table) + (b"\x00" * padding_needed)

        data_table = bytearray()
        data_offsets: List[int] = []
        param_lens: List[int] = []

        for entry in entries:
            align_padding = (4 - (len(data_table) % 4)) % 4
            if align_padding and len(data_table) > 0:
                data_table.extend(b"\x00" * align_padding)

            data_offsets.append(len(data_table))
            data_bytes, param_len = entry.get_data_bytes()
            param_lens.append(param_len)
            data_table.extend(data_bytes)

        index_table_size = num_entries * SFO_INDEX_ENTRY_SIZE
        key_table_offset = SFO_HEADER_SIZE + index_table_size
        data_table_offset = key_table_offset + len(key_table_padded)

        header = struct.pack(
            "<4sIIII",
            SFO_MAGIC,
            SFO_VERSION,
            key_table_offset,
            data_table_offset,
            num_entries,
        )

        index_table = bytearray()
        for i, entry in enumerate(entries):
            index_table.extend(
                struct.pack(
                    "<HHIII",
                    key_offsets[i],
                    entry.fmt,
                    param_lens[i],
                    entry.max_len,
                    data_offsets[i],
                )
            )

        return header + bytes(index_table) + key_table_padded + bytes(data_table)

    def save(self, path: str):
        with open(path, "wb") as f:
            f.write(self.build())


def create_ps2_classic_sfo(title: str, title_id: str, content_id: str, output_path: str) -> bytes:
    builder = SFOBuilder()
    builder.set_title(title)
    builder.set_title_id(title_id)
    builder.set_content_id(content_id)
    builder.save(output_path)
    return builder.build()