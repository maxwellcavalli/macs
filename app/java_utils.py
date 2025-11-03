from __future__ import annotations

from pathlib import Path
from typing import Optional
import re


def _expected_package(path: Path) -> Optional[str]:
    parts = path.parts
    try:
        idx = parts.index("java")
    except ValueError:
        return None
    pkg_parts = [segment for segment in parts[idx + 1 : -1] if segment and segment not in {"."}]
    if not pkg_parts:
        return ""
    return ".".join(pkg_parts)


def fix_java_package(path: Path) -> None:
    if path.suffix.lower() != ".java":
        return
    expected = _expected_package(path)
    if expected is None:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return

    lines = text.splitlines()
    trailing_newline = text.endswith("\n")

    pkg_idx = None
    current_pkg = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("package "):
            pkg_idx = idx
            current_pkg = stripped[len("package ") :].rstrip(";")
            break

    if expected == "":
        if pkg_idx is None:
            return
        del lines[pkg_idx]
        if pkg_idx < len(lines) and not lines[pkg_idx].strip():
            del lines[pkg_idx]
    else:
        package_line = f"package {expected};"
        if pkg_idx is not None:
            if current_pkg == expected:
                return
            lines[pkg_idx] = package_line
        else:
            insert_idx = 0
            while insert_idx < len(lines):
                stripped = lines[insert_idx].strip()
                if not stripped or stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                    insert_idx += 1
                    continue
                break
            lines.insert(insert_idx, package_line)
            lines.insert(insert_idx + 1, "")

    new_text = "\n".join(lines)
    if trailing_newline and not new_text.endswith("\n"):
        new_text += "\n"
    try:
        path.write_text(new_text, encoding="utf-8")
    except Exception:
        pass


def fix_java_filename(path: Path) -> Path:
    if path.suffix.lower() != ".java" or not path.exists():
        return path
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return path

    match = re.search(r"^\s*(?:public\s+)?(class|interface|enum|record)\s+([A-Za-z_][A-Za-z0-9_]*)", text, re.MULTILINE)
    if not match:
        return path
    class_name = match.group(2)
    expected_name = f"{class_name}.java"
    if path.name == expected_name:
        return path

    new_path = path.with_name(expected_name)

    try:
        if path.name.lower() == expected_name.lower():
            temp = path.with_name(f"{class_name}__tmp__.java")
            if temp.exists():
                temp.unlink()
            path.rename(temp)
            if new_path.exists():
                new_path.unlink()
            temp.rename(new_path)
        else:
            if new_path.exists():
                new_path.unlink()
            path.rename(new_path)
        return new_path
    except Exception:
        return path
