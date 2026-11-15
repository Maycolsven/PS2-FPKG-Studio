"""
sfo_builder.py - Constructor de archivos PARAM.SFO compatibles con PS4.

Genera archivos SFO binarios desde cero en Python puro, con los campos
necesarios para empaquetar juegos PS2 Classics en formato PS4 PKG.

Formato binario SFO:
    - Header (20 bytes): magic, versión, offsets, número de entradas
    - Index Table: 16 bytes por entrada (key_offset, param_format, param_len, param_max_len, data_offset)
    - Key Table: cadenas UTF-8 terminadas en null
    - Data Table: valores (cadenas con padding, enteros uint32 LE)

Referencia: https://www.psdevwiki.com/ps4/Param.sfo
"""

import struct
from typing import Dict, List, Tuple, Optional


# ── Constantes del formato SFO ──────────────────────────────────────────────

SFO_MAGIC = b'\x00PSF'
SFO_VERSION = 0x00000101

# Formatos de parámetro
PARAM_FMT_UTF8 = 0x0204      # Cadena UTF-8 terminada en null
PARAM_FMT_UINT32 = 0x0404    # Entero sin signo de 32 bits (little-endian)

# Tamaño del header SFO en bytes
SFO_HEADER_SIZE = 20          # magic(4) + version(4) + key_off(4) + data_off(4) + count(4)

# Tamaño de cada entrada en la tabla de índices
SFO_INDEX_ENTRY_SIZE = 16     # key_off(2) + fmt(2) + param_len(4) + param_max(4) + data_off(4)


class SFOEntry:
    """Representa una entrada individual dentro del archivo SFO.

    Attributes:
        key: Nombre del parámetro (e.g. "TITLE", "CONTENT_ID").
        fmt: Formato del valor (PARAM_FMT_UTF8 o PARAM_FMT_UINT32).
        value: Valor del parámetro (str para UTF-8, int para UINT32).
        max_len: Tamaño máximo reservado para el valor en la Data Table.
    """

    def __init__(self, key: str, fmt: int, value, max_len: int):
        self.key: str = key
        self.fmt: int = fmt
        self.value = value
        self.max_len: int = max_len

    def get_data_bytes(self) -> bytes:
        """Serializa el valor de la entrada a bytes según su formato.

        Returns:
            bytes: Datos del valor, con padding hasta max_len para cadenas
                   o como uint32 LE para enteros.

        Raises:
            ValueError: Si el valor codificado excede max_len.
        """
        if self.fmt == PARAM_FMT_UTF8:
            # Cadena UTF-8 terminada en null, con padding de ceros hasta max_len
            encoded = self.value.encode('utf-8') + b'\x00'
            if len(encoded) > self.max_len:
                raise ValueError(
                    f"El valor de '{self.key}' ({len(encoded)} bytes con null) "
                    f"excede max_len ({self.max_len} bytes)"
                )
            param_len = len(encoded)
            # Rellenar con ceros hasta max_len
            data = encoded + b'\x00' * (self.max_len - len(encoded))
            return data, param_len
        elif self.fmt == PARAM_FMT_UINT32:
            # Entero de 32 bits en little-endian (siempre 4 bytes)
            return struct.pack('<I', self.value), 4
        else:
            raise ValueError(f"Formato de parámetro desconocido: 0x{self.fmt:04X}")


class SFOBuilder:
    """Constructor de archivos PARAM.SFO para PS2 Classics en PS4.

    Inicializa con los campos por defecto requeridos para un PKG de
    PS2 Classics y permite personalizar título, title_id y content_id.

    Ejemplo de uso:
        >>> builder = SFOBuilder()
        >>> builder.set_title("Mi Juego PS2")
        >>> builder.set_title_id("CUSA12345")
        >>> builder.set_content_id("UP9000-CUSA12345_00-0000000000000001")
        >>> builder.save("param.sfo")
    """

    def __init__(self):
        """Inicializa el builder con los campos por defecto de PS2 Classics."""
        self._entries: Dict[str, SFOEntry] = {}
        self._init_default_entries()

    def _init_default_entries(self):
        """Configura las entradas SFO por defecto para un PS2 Classic.

        Los campos y sus tamaños máximos siguen la especificación de
        Sony para paquetes PS2 Classics en PS4.
        """
        # Campos de cadena (UTF-8)
        self._add_entry("APP_VER",        PARAM_FMT_UTF8,  "01.00",  8)
        self._add_entry("CATEGORY",       PARAM_FMT_UTF8,  "gd",     4)
        self._add_entry("CONTENT_ID",     PARAM_FMT_UTF8,  "",       48)
        self._add_entry("FORMAT",         PARAM_FMT_UTF8,  "obs",    4)
        self._add_entry("TITLE",          PARAM_FMT_UTF8,  "",       128)
        self._add_entry("TITLE_ID",       PARAM_FMT_UTF8,  "",       12)
        self._add_entry("VERSION",        PARAM_FMT_UTF8,  "01.00",  8)

        # Campos enteros (UINT32)
        self._add_entry("APP_TYPE",       PARAM_FMT_UINT32, 1,       4)
        self._add_entry("ATTRIBUTE",      PARAM_FMT_UINT32, 0,       4)
        self._add_entry("PARENTAL_LEVEL", PARAM_FMT_UINT32, 0,       4)

    def _add_entry(self, key: str, fmt: int, value, max_len: int):
        """Agrega o reemplaza una entrada en el diccionario interno.

        Args:
            key: Nombre del parámetro SFO.
            fmt: Formato (PARAM_FMT_UTF8 o PARAM_FMT_UINT32).
            value: Valor del parámetro.
            max_len: Tamaño máximo en bytes para la Data Table.
        """
        self._entries[key] = SFOEntry(key, fmt, value, max_len)

    def set_title(self, title: str):
        """Establece el título del juego.

        Args:
            title: Nombre del juego (máximo 127 caracteres ASCII/UTF-8).

        Raises:
            ValueError: Si el título codificado + null excede 128 bytes.
        """
        encoded_len = len(title.encode('utf-8')) + 1  # +1 por el null terminator
        if encoded_len > 128:
            raise ValueError(
                f"El título '{title[:50]}...' ({encoded_len} bytes con null) "
                f"excede el máximo de 128 bytes"
            )
        self._entries["TITLE"].value = title

    def set_title_id(self, title_id: str):
        """Establece el Title ID del juego (e.g. 'CUSA12345').

        Args:
            title_id: Identificador del título, típicamente 9 caracteres.

        Raises:
            ValueError: Si el title_id codificado + null excede 12 bytes.
        """
        encoded_len = len(title_id.encode('utf-8')) + 1
        if encoded_len > 12:
            raise ValueError(
                f"El title_id '{title_id}' ({encoded_len} bytes con null) "
                f"excede el máximo de 12 bytes"
            )
        self._entries["TITLE_ID"].value = title_id

    def set_content_id(self, content_id: str):
        """Establece el Content ID completo del paquete.

        Args:
            content_id: ID de contenido completo, e.g.
                        'UP9000-CUSA12345_00-0000000000000001' (máx 47 chars).

        Raises:
            ValueError: Si el content_id codificado + null excede 48 bytes.
        """
        encoded_len = len(content_id.encode('utf-8')) + 1
        if encoded_len > 48:
            raise ValueError(
                f"El content_id '{content_id}' ({encoded_len} bytes con null) "
                f"excede el máximo de 48 bytes"
            )
        self._entries["CONTENT_ID"].value = content_id

    def _get_sorted_entries(self) -> List[SFOEntry]:
        """Devuelve las entradas ordenadas alfabéticamente por clave.

        El formato SFO requiere que las claves estén en orden alfabético
        tanto en la Index Table como en la Key Table.

        Returns:
            Lista de SFOEntry ordenada por key.
        """
        return [self._entries[k] for k in sorted(self._entries.keys())]

    def build(self) -> bytes:
        """Construye el archivo SFO binario completo.

        Ensambla el header, la tabla de índices, la tabla de claves y
        la tabla de datos en un solo bloque de bytes.

        Returns:
            bytes: Contenido binario completo del archivo PARAM.SFO.

        Raises:
            ValueError: Si algún valor excede su tamaño máximo permitido.
        """
        entries = self._get_sorted_entries()
        num_entries = len(entries)

        # ── Paso 1: Construir la Key Table ───────────────────────────────
        # Cada clave es una cadena UTF-8 terminada en null
        key_table = bytearray()
        key_offsets: List[int] = []

        for entry in entries:
            key_offsets.append(len(key_table))
            key_table.extend(entry.key.encode('utf-8') + b'\x00')

        # Alinear la Key Table a 4 bytes para que la Data Table comience
        # en una dirección alineada
        key_table_padded = bytes(key_table)
        padding_needed = (4 - (len(key_table_padded) % 4)) % 4
        key_table_padded += b'\x00' * padding_needed

        # ── Paso 2: Construir la Data Table ──────────────────────────────
        data_table = bytearray()
        data_offsets: List[int] = []
        param_lens: List[int] = []

        for entry in entries:
            # Alinear cada entrada de datos a 4 bytes
            current_offset = len(data_table)
            align_padding = (4 - (current_offset % 4)) % 4
            if align_padding and current_offset > 0:
                data_table.extend(b'\x00' * align_padding)

            data_offsets.append(len(data_table))
            data_bytes, param_len = entry.get_data_bytes()
            param_lens.append(param_len)
            data_table.extend(data_bytes)

        data_table = bytes(data_table)

        # ── Paso 3: Calcular offsets del header ──────────────────────────
        index_table_size = num_entries * SFO_INDEX_ENTRY_SIZE
        key_table_offset = SFO_HEADER_SIZE + index_table_size
        data_table_offset = key_table_offset + len(key_table_padded)

        # ── Paso 4: Construir el Header ──────────────────────────────────
        header = struct.pack('<4sIIII',
            SFO_MAGIC,
            SFO_VERSION,
            key_table_offset,
            data_table_offset,
            num_entries,
        )

        # ── Paso 5: Construir la Index Table ─────────────────────────────
        index_table = bytearray()
        for i, entry in enumerate(entries):
            # Cada entrada: key_offset(u16) + fmt(u16) + param_len(u32)
            #              + param_max_len(u32) + data_offset(u32)
            index_entry = struct.pack('<HHIII',
                key_offsets[i],
                entry.fmt,
                param_lens[i],
                entry.max_len,
                data_offsets[i],
            )
            index_table.extend(index_entry)

        index_table = bytes(index_table)

        # ── Paso 6: Ensamblar el archivo completo ────────────────────────
        sfo_binary = header + index_table + key_table_padded + data_table
        return sfo_binary

    def save(self, path: str):
        """Construye y guarda el archivo SFO en disco.

        Args:
            path: Ruta del archivo de salida (e.g. 'param.sfo').

        Raises:
            ValueError: Si algún valor excede su tamaño máximo.
            OSError: Si no se puede escribir el archivo.
        """
        sfo_data = self.build()
        with open(path, 'wb') as f:
            f.write(sfo_data)


def create_ps2_classic_sfo(
    title: str,
    title_id: str,
    content_id: str,
    output_path: str,
) -> bytes:
    """Función de conveniencia para crear un PARAM.SFO de PS2 Classics.

    Crea un archivo SFO con los valores proporcionados y lo guarda
    en la ruta indicada.

    Args:
        title: Nombre del juego (e.g. "Shadow of the Colossus").
        title_id: Identificador CUSA (e.g. "CUSA12345").
        content_id: Content ID completo
                    (e.g. "UP9000-CUSA12345_00-0000000000000001").
        output_path: Ruta donde guardar el archivo SFO.

    Returns:
        bytes: Contenido binario del archivo SFO generado.

    Raises:
        ValueError: Si algún parámetro excede su longitud máxima.
        OSError: Si no se puede escribir el archivo de salida.

    Ejemplo:
        >>> sfo_data = create_ps2_classic_sfo(
        ...     title="Mi Juego PS2",
        ...     title_id="CUSA99999",
        ...     content_id="UP9000-CUSA99999_00-PS2CLASSICGAME01",
        ...     output_path="param.sfo",
        ... )
    """
    builder = SFOBuilder()
    builder.set_title(title)
    builder.set_title_id(title_id)
    builder.set_content_id(content_id)
    builder.save(output_path)
    return builder.build()


# ── Ejecución directa para pruebas rápidas ──────────────────────────────────

if __name__ == "__main__":
    import sys
    import os

    # Valores de ejemplo para prueba
    test_title = "PS2 Test Game"
    test_title_id = "CUSA00001"
    test_content_id = "UP9000-CUSA00001_00-PS2CLASSICTEST01"

    output = os.path.join(os.path.dirname(__file__), "test_param.sfo")

    sfo_bytes = create_ps2_classic_sfo(
        title=test_title,
        title_id=test_title_id,
        content_id=test_content_id,
        output_path=output,
    )

    print(f"SFO generado: {output}")
    print(f"Tamaño: {len(sfo_bytes)} bytes")

    # Verificación básica del header
    magic = sfo_bytes[:4]
    version = struct.unpack_from('<I', sfo_bytes, 4)[0]
    key_off = struct.unpack_from('<I', sfo_bytes, 8)[0]
    data_off = struct.unpack_from('<I', sfo_bytes, 12)[0]
    count = struct.unpack_from('<I', sfo_bytes, 16)[0]

    print(f"Magic: {magic}")
    print(f"Version: 0x{version:08X}")
    print(f"Key Table Offset: {key_off}")
    print(f"Data Table Offset: {data_off}")
    print(f"Entradas: {count}")

    # Verificar orden alfabético de las claves
    keys = []
    for i in range(count):
        idx_base = SFO_HEADER_SIZE + i * SFO_INDEX_ENTRY_SIZE
        k_off = struct.unpack_from('<H', sfo_bytes, idx_base)[0]
        # Leer la clave desde la Key Table
        abs_k_off = key_off + k_off
        end = sfo_bytes.index(b'\x00', abs_k_off)
        key_name = sfo_bytes[abs_k_off:end].decode('utf-8')
        keys.append(key_name)

    print(f"Claves (orden): {keys}")
    assert keys == sorted(keys), "ERROR: Las claves NO están en orden alfabético"
    print("✓ Claves en orden alfabético correcto")
