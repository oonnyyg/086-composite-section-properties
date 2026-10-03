"""Command line entry: python -m section_props INPUT.json --out-dir DIR."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from .core import SectionError, SectionResult, load_sections

_CSV_FIELDS = (
    "rect_id",
    "kind",
    "parent_id",
    "signed_area_mm2",
    "cx_mm",
    "cy_mm",
    "ix_mm4",
    "iy_mm4",
    "ixy_mm4",
)


def _format(value: float) -> str:
    return format(value, ".17g")


def _write_section_csv(path: Path, result: SectionResult) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(_CSV_FIELDS)
        for comp in result.components:
            writer.writerow(
                [
                    comp.rect_id,
                    comp.kind,
                    comp.parent_id or "",
                    _format(comp.signed_area),
                    _format(comp.cx),
                    _format(comp.cy),
                    _format(comp.ix),
                    _format(comp.iy),
                    _format(comp.ixy),
                ]
            )


def _summary_entry(result: SectionResult) -> dict[str, object]:
    return {
        "id": result.section_id,
        "area_mm2": result.area,
        "centroid": {"cx_mm": result.cx, "cy_mm": result.cy},
        "ix_mm4": result.ix,
        "iy_mm4": result.iy,
        "ixy_mm4": result.ixy,
        "imax_mm4": result.imax,
        "imin_mm4": result.imin,
        "components_csv": f"{result.section_id}.csv",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m section_props",
        description="Compute geometric properties of composite sections "
        "with rectangular holes (millimetre units).",
    )
    parser.add_argument("input", help="path to the batch JSON file")
    parser.add_argument(
        "--out-dir",
        required=True,
        help="directory receiving per-section CSV files and summary.json",
    )
    args = parser.parse_args(argv)

    try:
        text = Path(args.input).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read input file: {exc}", file=sys.stderr)
        return 2

    try:
        results = load_sections(text)
    except SectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Validation and computation succeeded for the whole batch; only now
    # create the output directory and write results.
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(results, key=lambda item: item.section_id)
    for result in ordered:
        _write_section_csv(out_dir / f"{result.section_id}.csv", result)
    summary = {
        "units": {"length": "mm", "area": "mm^2", "second_moment": "mm^4"},
        "sections": [_summary_entry(result) for result in ordered],
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(ordered)} section(s) to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
