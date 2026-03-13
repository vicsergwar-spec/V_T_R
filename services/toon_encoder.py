"""
Encoder TOON (Text Object Notation) — formato compacto optimizado para LLMs.

Implementación propia porque toon-format v0.1.0 solo tiene stubs.
Sigue la especificación descrita en los docstrings del paquete oficial.

Formato:
  - Objetos planos:       key: value
  - Objetos anidados:     key:\n  subkey: value
  - Arrays simples:       key[n]: v1,v2,...
  - Arrays tabulares:     key[n]{col1,col2}:\n  v1,v2\n  v3,v4
  - Primitivos raíz:      valor directo
"""

from __future__ import annotations

from typing import Any


def encode(value: Any, *, indent: int = 2, delimiter: str = ",") -> str:
    """Convierte un valor Python (JSON-serializable) a formato TOON."""
    return _encode_value(value, depth=0, indent=indent, delimiter=delimiter)


def dumps(value: Any, *, indent: int = 2, delimiter: str = ",") -> str:
    """Alias amigable de encode()."""
    return encode(value, indent=indent, delimiter=delimiter)


# ── internos ──────────────────────────────────────────────────────────

def _encode_value(value: Any, depth: int, indent: int, delimiter: str) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return _encode_string(value)
    if isinstance(value, list):
        return _encode_array(value, depth, indent, delimiter)
    if isinstance(value, dict):
        return _encode_object(value, depth, indent, delimiter)
    return _encode_string(str(value))


def _encode_string(s: str) -> str:
    """Strings que contengan delimitadores o newlines se entrecomillan."""
    if not s:
        return '""'
    needs_quote = any(c in s for c in (",", "\t", "|", "\n", '"'))
    if needs_quote:
        escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    return s


def _encode_object(obj: dict, depth: int, indent: int, delimiter: str) -> str:
    if not obj:
        return "{}"
    pad = " " * (indent * (depth + 1))
    lines = []
    for key, val in obj.items():
        if isinstance(val, list) and val and all(isinstance(v, dict) for v in val):
            # Array tabular
            lines.append(_encode_tabular(key, val, depth, indent, delimiter))
        elif isinstance(val, list):
            # Array simple
            encoded_items = [_encode_value(v, depth + 1, indent, delimiter) for v in val]
            inline = f"{delimiter}".join(encoded_items)
            lines.append(f"{pad}{key}[{len(val)}]: {inline}")
        elif isinstance(val, dict):
            sub = _encode_object(val, depth + 1, indent, delimiter)
            lines.append(f"{pad}{key}:\n{sub}")
        else:
            lines.append(f"{pad}{key}: {_encode_value(val, depth + 1, indent, delimiter)}")
    return "\n".join(lines)


def _encode_tabular(key: str, rows: list[dict], depth: int, indent: int, delimiter: str) -> str:
    """Codifica un array de objetos uniformes como tabla TOON."""
    pad = " " * (indent * (depth + 1))
    row_pad = " " * (indent * (depth + 2))

    # Recolectar todas las columnas (unión de keys)
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for k in row:
            if k not in seen:
                columns.append(k)
                seen.add(k)

    header = f"{delimiter}".join(columns)
    data_lines = []
    for row in rows:
        vals = []
        for col in columns:
            v = row.get(col)
            vals.append(_encode_value(v, depth + 2, indent, delimiter))
        data_lines.append(f"{row_pad}{delimiter.join(vals)}")

    result = f"{pad}{key}[{len(rows)}]{{{header}}}:\n"
    result += "\n".join(data_lines)
    return result


def _encode_array(arr: list, depth: int, indent: int, delimiter: str) -> str:
    if not arr:
        return "[]"

    # Si todos son dicts → tabular (root-level)
    if all(isinstance(v, dict) for v in arr):
        return _encode_tabular_root(arr, depth, indent, delimiter)

    # Array simple inline
    encoded = [_encode_value(v, depth, indent, delimiter) for v in arr]
    return f"[{len(arr)}]: {delimiter.join(encoded)}"


def _encode_tabular_root(rows: list[dict], depth: int, indent: int, delimiter: str) -> str:
    """Tabla TOON a nivel raíz (sin key padre)."""
    pad = " " * (indent * (depth + 1))

    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for k in row:
            if k not in seen:
                columns.append(k)
                seen.add(k)

    header = f"{delimiter}".join(columns)
    data_lines = []
    for row in rows:
        vals = []
        for col in columns:
            v = row.get(col)
            vals.append(_encode_value(v, depth + 1, indent, delimiter))
        data_lines.append(f"{pad}{delimiter.join(vals)}")

    result = f"[{len(rows)}]{{{header}}}:\n"
    result += "\n".join(data_lines)
    return result
