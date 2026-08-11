"""Display-safe image metadata helpers."""
from __future__ import annotations

import struct
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, Optional, Union

from PyQt6.QtGui import QImageReader

PathLike = Union[str, Path]

TIFF_TYPE_SIZES = {
    1: 1,
    2: 1,
    3: 2,
    4: 4,
    5: 8,
    7: 1,
    9: 4,
    10: 8,
}

EXIF_LABELS = {
    0x010F: "Camera make",
    0x0110: "Camera model",
    0x0112: "Orientation",
    0x0131: "Software",
    0x0132: "Date taken",
    0x829A: "Exposure time",
    0x829D: "F-number",
    0x8827: "ISO",
    0x9003: "Date original",
    0x920A: "Focal length",
    0xA434: "Lens model",
}


def read_image_metadata(image_path: PathLike) -> dict[str, str]:
    """Return image details suitable for display in the interface."""
    path = Path(image_path)
    metadata: dict[str, str] = {
        "Filename": path.name,
        "Path": str(path),
    }

    try:
        stat = path.stat()
    except OSError:
        metadata["Status"] = "File is not readable"
        return metadata

    metadata["Size"] = _format_bytes(stat.st_size)
    reader = QImageReader(str(path))
    image_size = reader.size()
    if image_size.isValid():
        metadata["Dimensions"] = f"{image_size.width()} x {image_size.height()}"
    image_format = bytes(reader.format()).decode("ascii", errors="ignore").upper()
    if image_format:
        metadata["Format"] = image_format

    metadata.update(_read_exif(path))
    return {key: value for key, value in metadata.items() if value}


def _read_exif(path: Path) -> dict[str, str]:
    try:
        data = path.read_bytes()
    except OSError:
        return {}

    exif = _extract_jpeg_exif(data)
    if exif is None:
        return {}
    return _parse_tiff_exif(exif)


def _extract_jpeg_exif(data: bytes) -> Optional[bytes]:
    if not data.startswith(b"\xff\xd8"):
        return None

    offset = 2
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            return None
        marker = data[offset + 1]
        offset += 2
        if marker == 0xDA:
            return None
        if offset + 2 > len(data):
            return None
        segment_length = int.from_bytes(data[offset:offset + 2], "big")
        segment_start = offset + 2
        segment_end = offset + segment_length
        if segment_end > len(data):
            return None
        segment = data[segment_start:segment_end]
        if marker == 0xE1 and segment.startswith(b"Exif\x00\x00"):
            return segment[6:]
        offset = segment_end
    return None


def _parse_tiff_exif(data: bytes) -> dict[str, str]:
    if len(data) < 8:
        return {}

    byte_order = data[:2]
    if byte_order == b"II":
        endian = "<"
    elif byte_order == b"MM":
        endian = ">"
    else:
        return {}

    if _unpack(endian, "H", data, 2) != 42:
        return {}

    entries: dict[int, Any] = {}
    first_ifd = _unpack(endian, "I", data, 4)
    _read_ifd(data, endian, first_ifd, entries)
    exif_ifd = entries.get(0x8769)
    if isinstance(exif_ifd, int):
        _read_ifd(data, endian, exif_ifd, entries)

    return {
        label: _format_exif_value(tag, entries[tag])
        for tag, label in EXIF_LABELS.items()
        if tag in entries and _format_exif_value(tag, entries[tag])
    }


def _read_ifd(data: bytes, endian: str, offset: int, entries: Dict[int, Any]) -> None:
    if offset <= 0 or offset + 2 > len(data):
        return

    count = _unpack(endian, "H", data, offset)
    cursor = offset + 2
    for _ in range(count):
        if cursor + 12 > len(data):
            return
        tag = _unpack(endian, "H", data, cursor)
        field_type = _unpack(endian, "H", data, cursor + 2)
        value_count = _unpack(endian, "I", data, cursor + 4)
        raw_value = data[cursor + 8:cursor + 12]
        entries[tag] = _decode_tiff_value(data, endian, field_type, value_count, raw_value)
        cursor += 12


def _decode_tiff_value(
    data: bytes,
    endian: str,
    field_type: int,
    count: int,
    raw_value: bytes,
) -> Any:
    type_size = TIFF_TYPE_SIZES.get(field_type)
    if type_size is None:
        return None

    total_size = type_size * count
    if total_size <= 4:
        value_bytes = raw_value[:total_size]
    else:
        value_offset = struct.unpack(f"{endian}I", raw_value)[0]
        if value_offset < 0 or value_offset + total_size > len(data):
            return None
        value_bytes = data[value_offset:value_offset + total_size]

    if field_type == 2:
        return value_bytes.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()
    if field_type == 3:
        values = struct.unpack(f"{endian}{count}H", value_bytes)
    elif field_type == 4:
        values = struct.unpack(f"{endian}{count}I", value_bytes)
    elif field_type == 5:
        values = [
            Fraction(
                struct.unpack(f"{endian}I", value_bytes[index:index + 4])[0],
                struct.unpack(f"{endian}I", value_bytes[index + 4:index + 8])[0] or 1,
            )
            for index in range(0, len(value_bytes), 8)
        ]
    elif field_type == 9:
        values = struct.unpack(f"{endian}{count}i", value_bytes)
    elif field_type == 10:
        values = [
            Fraction(
                struct.unpack(f"{endian}i", value_bytes[index:index + 4])[0],
                struct.unpack(f"{endian}i", value_bytes[index + 4:index + 8])[0] or 1,
            )
            for index in range(0, len(value_bytes), 8)
        ]
    else:
        values = tuple(value_bytes)

    if count == 1 and isinstance(values, tuple):
        return values[0]
    if count == 1 and isinstance(values, list):
        return values[0]
    return values


def _format_exif_value(tag: int, value: Any) -> str:
    if value is None:
        return ""
    if tag == 0x829A and isinstance(value, Fraction):
        return f"1/{round(value.denominator / value.numerator)} sec" if value.numerator else ""
    if tag == 0x829D and isinstance(value, Fraction):
        return f"f/{float(value):.1f}"
    if tag == 0x920A and isinstance(value, Fraction):
        return f"{float(value):.1f} mm"
    if isinstance(value, Fraction):
        return str(float(value))
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return str(value).strip()


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _unpack(endian: str, fmt: str, data: bytes, offset: int) -> int:
    return struct.unpack_from(f"{endian}{fmt}", data, offset)[0]
