"""Command-line interface: validate, compute, and write CSV/JSON outputs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from .geometry import SectionResult, compute_section
from .validation import SectionError, parse_document

CSV_FIELDS = [
    "section_id",
    "rect_id",
    "parent_id",
    "signed_area_mm2",
    "ix_mm4",
    "iy_mm4",
    "ixy_mm4",
]


def _fmt(value: float) -> str:
    return format(value, ".17g")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m section_props",
        description="Compute geometric properties of composite sections.",
    )
    parser.add_argument("input", help="path to the input JSON document")
    parser.add_argument("outdir", help="directory for CSV and summary JSON output")
    args = parser.parse_args(argv)

    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read input: {exc}", file=sys.stderr)
        return 2

    try:
        sections = parse_document(data)
    except SectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    results = [
        compute_section(sid, solids, holes) for sid, solids, holes in sections
    ]
    # Stable output ordering by section id.
    results.sort(key=lambda r: r.section_id)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    for result in results:
        _write_csv(outdir / f"{result.section_id}.csv", result)
    _write_summary(outdir / "summary.json", results)
    return 0


def _write_csv(path: Path, result: SectionResult) -> None:
    rows = sorted(result.contributions, key=lambda c: c.rect_id)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_FIELDS)
        for c in rows:
            writer.writerow(
                [
                    result.section_id,
                    c.rect_id,
                    c.parent_id or "",
                    _fmt(c.signed_area),
                    _fmt(c.ix),
                    _fmt(c.iy),
                    _fmt(c.ixy),
                ]
            )


def _write_summary(path: Path, results: list[SectionResult]) -> None:
    summary = {
        "units": {"length": "mm", "area": "mm^2", "second_moment": "mm^4"},
        "sections": [
            {
                "id": r.section_id,
                "area_mm2": r.area,
                "centroid_x_mm": r.centroid_x,
                "centroid_y_mm": r.centroid_y,
                "ix_mm4": r.ix,
                "iy_mm4": r.iy,
                "ixy_mm4": r.ixy,
                "imax_mm4": r.imax,
                "imin_mm4": r.imin,
            }
            for r in results
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
