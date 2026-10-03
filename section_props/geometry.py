"""Geometric property computation for composite rectangular sections.

All lengths are in millimetres. Areas are mm^2, second moments of area
are mm^4. Rectangles are axis-aligned, defined by centre coordinates and
positive width (x extent) / height (y extent).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rect:
    """An axis-aligned rectangle. ``sign`` is +1 for solid, -1 for a hole."""

    rect_id: str
    cx: float
    cy: float
    width: float
    height: float
    sign: int = 1

    @property
    def area(self) -> float:
        return self.sign * self.width * self.height

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


@dataclass
class RectContribution:
    """Signed contribution of one rectangle to the section properties."""

    rect_id: str
    parent_id: str | None
    signed_area: float
    ix: float  # contribution to Ix about the global centroidal x-axis
    iy: float  # contribution to Iy about the global centroidal y-axis
    ixy: float  # contribution to the product of inertia


@dataclass
class SectionResult:
    section_id: str
    area: float
    centroid_x: float
    centroid_y: float
    ix: float
    iy: float
    ixy: float
    imax: float
    imin: float
    contributions: list[RectContribution] = field(default_factory=list)


def compute_section(
    section_id: str,
    solids: list[Rect],
    holes: list[tuple[str, Rect]],
) -> SectionResult:
    """Compute properties of one section.

    ``solids`` are solid rectangles; ``holes`` is a list of
    ``(parent_solid_id, hole_rect)`` pairs.
    """
    rects: list[tuple[Rect, str | None]] = [(r, None) for r in solids]
    rects += [(h, parent) for parent, h in holes]

    area = sum(r.area for r, _ in rects)
    sx = sum(r.area * r.cx for r, _ in rects)
    sy = sum(r.area * r.cy for r, _ in rects)
    gx = sx / area
    gy = sy / area

    contributions: list[RectContribution] = []
    ix = iy = ixy = 0.0
    for r, parent in rects:
        # Rectangle's own centroidal second moments (positive), times sign.
        own_ix = r.sign * r.width * r.height**3 / 12.0
        own_iy = r.sign * r.height * r.width**3 / 12.0
        dx = r.cx - gx
        dy = r.cy - gy
        # Parallel-axis transfer to the global centroid, signed by area.
        c_ix = own_ix + r.area * dy * dy
        c_iy = own_iy + r.area * dx * dx
        c_ixy = r.area * dx * dy
        ix += c_ix
        iy += c_iy
        ixy += c_ixy
        contributions.append(
            RectContribution(
                rect_id=r.rect_id,
                parent_id=parent,
                signed_area=r.area,
                ix=c_ix,
                iy=c_iy,
                ixy=c_ixy,
            )
        )

    # Principal second moments of area (axis directions not required).
    avg = (ix + iy) / 2.0
    radius = (((ix - iy) / 2.0) ** 2 + ixy**2) ** 0.5
    imax = avg + radius
    imin = avg - radius

    return SectionResult(
        section_id=section_id,
        area=area,
        centroid_x=gx,
        centroid_y=gy,
        ix=ix,
        iy=iy,
        ixy=ixy,
        imax=imax,
        imin=imin,
        contributions=contributions,
    )
