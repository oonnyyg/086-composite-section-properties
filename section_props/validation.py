"""Input validation for composite section JSON documents.

Raises :class:`SectionError` with the section id and rectangle id in the
message so failures can be located precisely.
"""

from __future__ import annotations

import math
from typing import Any

from .geometry import Rect


class SectionError(ValueError):
    """Raised when a section definition is invalid."""


def _fail(section: str, rect: str | None, msg: str) -> None:
    where = f"section '{section}'"
    if rect is not None:
        where += f", rectangle '{rect}'"
    raise SectionError(f"{where}: {msg}")


def _check_number(value: Any, name: str, section: str, rect: str | None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(section, rect, f"'{name}' must be a number, got {value!r}")
    fval = float(value)
    if not math.isfinite(fval):
        _fail(section, rect, f"'{name}' must be finite, got {value!r}")
    return fval


def _parse_rect(obj: Any, section: str, rect_id: str, sign: int) -> Rect:
    if not isinstance(obj, dict):
        _fail(section, rect_id, "rectangle definition must be an object")
    cx = _check_number(obj.get("cx"), "cx", section, rect_id)
    cy = _check_number(obj.get("cy"), "cy", section, rect_id)
    width = _check_number(obj.get("width"), "width", section, rect_id)
    height = _check_number(obj.get("height"), "height", section, rect_id)
    if width <= 0:
        _fail(section, rect_id, f"'width' must be positive, got {width}")
    if height <= 0:
        _fail(section, rect_id, f"'height' must be positive, got {height}")
    return Rect(rect_id=rect_id, cx=cx, cy=cy, width=width, height=height, sign=sign)


def _overlap_interior(a: Rect, b: Rect) -> bool:
    """True if two rectangles overlap with positive area (touching is OK)."""
    return (
        a.xmin < b.xmax
        and b.xmin < a.xmax
        and a.ymin < b.ymax
        and b.ymin < a.ymax
    )


def _inside(inner: Rect, outer: Rect) -> bool:
    """True if ``inner`` lies fully within ``outer`` (boundary contact OK)."""
    return (
        inner.xmin >= outer.xmin
        and inner.xmax <= outer.xmax
        and inner.ymin >= outer.ymin
        and inner.ymax <= outer.ymax
    )


def parse_document(data: Any) -> list[tuple[str, list[Rect], list[tuple[str, Rect]]]]:
    """Validate the whole document; return parsed sections in input order."""
    if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
        raise SectionError("document must be an object with a 'sections' list")
    sections = []
    seen_sections: set[str] = set()
    for entry in data["sections"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise SectionError("each section must be an object with a string 'id'")
        sid = entry["id"]
        if sid in seen_sections:
            _fail(sid, None, "duplicate section id")
        seen_sections.add(sid)
        sections.append(_parse_section(entry, sid))
    return sections


def _parse_section(entry: dict, sid: str) -> tuple[str, list[Rect], list[tuple[str, Rect]]]:
    rects_obj = entry.get("rectangles")
    if not isinstance(rects_obj, list) or not rects_obj:
        _fail(sid, None, "'rectangles' must be a non-empty list")

    solids: list[Rect] = []
    holes: list[tuple[str, Rect]] = []
    seen_ids: set[str] = set()
    by_parent: dict[str, list[Rect]] = {}

    for robj in rects_obj:
        rid = robj.get("id") if isinstance(robj, dict) else None
        if not isinstance(rid, str):
            _fail(sid, None, "each rectangle must have a string 'id'")
        if rid in seen_ids:
            _fail(sid, rid, "duplicate rectangle id")
        seen_ids.add(rid)
        solid = _parse_rect(robj, sid, rid, sign=1)
        for other in solids:
            if _overlap_interior(solid, other):
                _fail(sid, rid, f"solid rectangle overlaps '{other.rect_id}'")
        solids.append(solid)

        holes_obj = robj.get("holes", [])
        if not isinstance(holes_obj, list):
            _fail(sid, rid, "'holes' must be a list")
        for hobj in holes_obj:
            hid = hobj.get("id") if isinstance(hobj, dict) else None
            if not isinstance(hid, str):
                _fail(sid, rid, "each hole must have a string 'id'")
            if hid in seen_ids:
                _fail(sid, hid, "duplicate rectangle id")
            seen_ids.add(hid)
            hole = _parse_rect(hobj, sid, hid, sign=-1)
            if not _inside(hole, solid):
                _fail(sid, hid, f"hole is not fully inside solid '{rid}'")
            for other in by_parent.setdefault(rid, []):
                if _overlap_interior(hole, other):
                    _fail(sid, hid, f"hole overlaps hole '{other.rect_id}'")
            by_parent[rid].append(hole)
            holes.append((rid, hole))

    area = sum(r.area for r in solids) + sum(h.area for _, h in holes)
    if area <= 0:
        _fail(sid, None, "net effective area must be positive")
    return sid, solids, holes
