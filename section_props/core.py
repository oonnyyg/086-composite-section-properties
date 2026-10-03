"""Geometry and validation for composite sections built from rectangles.

All lengths are millimetres. Areas are mm^2, second moments of area are
mm^4. Rectangles are axis-aligned and defined by centre plus width/height.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field


class SectionError(ValueError):
    """Raised when the input batch or a section is invalid."""


@dataclass(frozen=True)
class Rect:
    rect_id: str
    cx: float
    cy: float
    width: float
    height: float

    @property
    def xmin(self) -> float:
        return self.cx - self.width / 2.0

    @property
    def xmax(self) -> float:
        return self.cx + self.width / 2.0

    @property
    def ymin(self) -> float:
        return self.cy - self.height / 2.0

    @property
    def ymax(self) -> float:
        return self.cy + self.height / 2.0

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass(frozen=True)
class ComponentResult:
    """Signed contribution of one rectangle (solid positive, hole negative)."""

    rect_id: str
    kind: str  # "solid" or "hole"
    parent_id: str | None
    signed_area: float
    cx: float
    cy: float
    ix: float  # contribution to Ix about the global centroidal axis
    iy: float
    ixy: float


@dataclass(frozen=True)
class SectionResult:
    section_id: str
    area: float
    cx: float
    cy: float
    ix: float
    iy: float
    ixy: float
    imax: float
    imin: float
    components: tuple[ComponentResult, ...] = field(default_factory=tuple)


def _rects_overlap(a: Rect, b: Rect) -> bool:
    """True if interiors overlap (boundary contact is allowed)."""
    return (
        a.xmin < b.xmax
        and b.xmin < a.xmax
        and a.ymin < b.ymax
        and b.ymin < a.ymax
    )


def _hole_inside(hole: Rect, solid: Rect) -> bool:
    return (
        solid.xmin <= hole.xmin
        and hole.xmax <= solid.xmax
        and solid.ymin <= hole.ymin
        and hole.ymax <= solid.ymax
    )


def _check_finite_number(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SectionError(f"{where}: value {value!r} is not a number")
    result = float(value)
    if not math.isfinite(result):
        raise SectionError(f"{where}: value {value!r} is not finite")
    return result


def _parse_rect(data: object, where: str) -> Rect:
    if not isinstance(data, dict):
        raise SectionError(f"{where}: rectangle entry must be an object")
    rect_id = data.get("id")
    if not isinstance(rect_id, str) or not rect_id:
        raise SectionError(f"{where}: rectangle id must be a non-empty string")
    rect_where = f"{where} rectangle {rect_id!r}"
    cx = _check_finite_number(data.get("cx"), f"{rect_where} cx")
    cy = _check_finite_number(data.get("cy"), f"{rect_where} cy")
    width = _check_finite_number(data.get("width"), f"{rect_where} width")
    height = _check_finite_number(data.get("height"), f"{rect_where} height")
    if width <= 0.0:
        raise SectionError(f"{rect_where}: width must be positive, got {width}")
    if height <= 0.0:
        raise SectionError(f"{rect_where}: height must be positive, got {height}")
    return Rect(rect_id=rect_id, cx=cx, cy=cy, width=width, height=height)


def _validate_section(
    section: object, index: int
) -> tuple[str, list[tuple[Rect, list[Rect]]]]:
    where = f"section[{index}]"
    if not isinstance(section, dict):
        raise SectionError(f"{where}: section entry must be an object")
    section_id = section.get("id")
    if not isinstance(section_id, str) or not section_id:
        raise SectionError(f"{where}: section id must be a non-empty string")
    where = f"section {section_id!r}"
    rects_data = section.get("rectangles")
    if not isinstance(rects_data, list) or not rects_data:
        raise SectionError(f"{where}: 'rectangles' must be a non-empty list")

    solids: list[Rect] = []
    holes_by_parent: dict[str, list[Rect]] = {}
    seen_ids: set[str] = set()
    for rect_data in rects_data:
        if not isinstance(rect_data, dict):
            raise SectionError(f"{where}: rectangle entry must be an object")
        solid = _parse_rect(rect_data, where)
        if solid.rect_id in seen_ids:
            raise SectionError(
                f"{where} rectangle {solid.rect_id!r}: duplicate rectangle id"
            )
        seen_ids.add(solid.rect_id)
        holes_data = rect_data.get("holes", [])
        if not isinstance(holes_data, list):
            raise SectionError(
                f"{where} rectangle {solid.rect_id!r}: 'holes' must be a list"
            )
        holes: list[Rect] = []
        for hole_data in holes_data:
            hole = _parse_rect(
                hole_data, f"{where} rectangle {solid.rect_id!r} hole"
            )
            if hole.rect_id in seen_ids:
                raise SectionError(
                    f"{where} rectangle {hole.rect_id!r}: duplicate rectangle id"
                )
            seen_ids.add(hole.rect_id)
            holes.append(hole)
        solids.append(solid)
        holes_by_parent[solid.rect_id] = holes

    for i, first in enumerate(solids):
        for second in solids[i + 1 :]:
            if _rects_overlap(first, second):
                raise SectionError(
                    f"{where}: solid rectangles {first.rect_id!r} and "
                    f"{second.rect_id!r} overlap"
                )

    for solid in solids:
        holes = holes_by_parent[solid.rect_id]
        for hole in holes:
            if not _hole_inside(hole, solid):
                raise SectionError(
                    f"{where} rectangle {hole.rect_id!r}: hole is not fully "
                    f"inside solid rectangle {solid.rect_id!r}"
                )
        for i, first in enumerate(holes):
            for second in holes[i + 1 :]:
                if _rects_overlap(first, second):
                    raise SectionError(
                        f"{where}: holes {first.rect_id!r} and "
                        f"{second.rect_id!r} of solid rectangle "
                        f"{solid.rect_id!r} overlap"
                    )

    return section_id, [
        (solid, holes_by_parent[solid.rect_id]) for solid in solids
    ]


def compute_section(
    section_id: str, parts: list[tuple[Rect, list[Rect]]]
) -> SectionResult:
    """Compute area, centroid and second moments of one validated section."""
    signed_parts: list[tuple[Rect, float, str | None]] = []
    for solid, holes in parts:
        signed_parts.append((solid, 1.0, None))
        for hole in holes:
            signed_parts.append((hole, -1.0, solid.rect_id))

    area = 0.0
    moment_x = 0.0  # signed integral of y dA
    moment_y = 0.0  # signed integral of x dA
    for rect, sign, _ in signed_parts:
        signed_area = sign * rect.area
        area += signed_area
        moment_x += signed_area * rect.cy
        moment_y += signed_area * rect.cx
    if area <= 0.0:
        raise SectionError(
            f"section {section_id!r}: total effective area must be positive, "
            f"got {area}"
        )
    cx = moment_y / area
    cy = moment_x / area

    ix = 0.0
    iy = 0.0
    ixy = 0.0
    components: list[ComponentResult] = []
    for rect, sign, parent_id in signed_parts:
        dx = rect.cx - cx
        dy = rect.cy - cy
        # Own centroidal second moments plus parallel-axis transfer term.
        comp_ix = sign * (rect.width * rect.height**3 / 12.0 + rect.area * dy * dy)
        comp_iy = sign * (rect.height * rect.width**3 / 12.0 + rect.area * dx * dx)
        comp_ixy = sign * rect.area * dx * dy
        ix += comp_ix
        iy += comp_iy
        ixy += comp_ixy
        components.append(
            ComponentResult(
                rect_id=rect.rect_id,
                kind="solid" if sign > 0 else "hole",
                parent_id=parent_id,
                signed_area=sign * rect.area,
                cx=rect.cx,
                cy=rect.cy,
                ix=comp_ix,
                iy=comp_iy,
                ixy=comp_ixy,
            )
        )

    # Principal second moments from Ix, Iy, Ixy (Ixy = integral of x*y dA).
    mean = (ix + iy) / 2.0
    radius = math.hypot((ix - iy) / 2.0, ixy)
    imax = mean + radius
    imin = mean - radius

    return SectionResult(
        section_id=section_id,
        area=area,
        cx=cx,
        cy=cy,
        ix=ix,
        iy=iy,
        ixy=ixy,
        imax=imax,
        imin=imin,
        components=tuple(components),
    )


def load_sections(text: str) -> list[SectionResult]:
    """Parse the batch JSON and compute every section; fail as a whole."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SectionError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
        raise SectionError("top level must be an object with a 'sections' list")
    if not data["sections"]:
        raise SectionError("'sections' must not be empty")

    seen_ids: set[str] = set()
    results: list[SectionResult] = []
    for index, section in enumerate(data["sections"]):
        section_id, parts = _validate_section(section, index)
        if section_id in seen_ids:
            raise SectionError(f"section {section_id!r}: duplicate section id")
        seen_ids.add(section_id)
        results.append(compute_section(section_id, parts))
    return results
