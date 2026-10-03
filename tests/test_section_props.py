"""Tests for the section_props package (standard-library unittest)."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from section_props import SectionError, load_sections  # noqa: E402

TOL = 1e-9


def make_section(rects, section_id="S1"):
    return {"id": section_id, "rectangles": rects}


def batch(*sections):
    return json.dumps({"sections": list(sections)})


def assert_close(test, actual, expected):
    test.assertLessEqual(
        abs(actual - expected),
        1e-8 * max(1.0, abs(expected)),
        f"{actual!r} != {expected!r}",
    )


class GeometryTests(unittest.TestCase):
    def test_single_solid_rectangle(self):
        result = load_sections(
            batch(make_section([{"id": "a", "cx": 10, "cy": -5,
                                 "width": 40, "height": 20}]))
        )[0]
        assert_close(self, result.area, 800.0)
        assert_close(self, result.cx, 10.0)
        assert_close(self, result.cy, -5.0)
        assert_close(self, result.ix, 40 * 20**3 / 12)
        assert_close(self, result.iy, 20 * 40**3 / 12)
        assert_close(self, result.ixy, 0.0)

    def test_eccentric_hole(self):
        # 100x80 solid at origin, 20x10 hole centred at (30, 15).
        result = load_sections(
            batch(make_section([
                {"id": "plate", "cx": 0, "cy": 0, "width": 100, "height": 80,
                 "holes": [{"id": "h1", "cx": 30, "cy": 15,
                            "width": 20, "height": 10}]},
            ]))
        )[0]
        area = 8000.0 - 200.0
        cx = -(200.0 * 30.0) / area
        cy = -(200.0 * 15.0) / area
        assert_close(self, result.area, area)
        assert_close(self, result.cx, cx)
        assert_close(self, result.cy, cy)
        ix = (100 * 80**3 / 12 + 8000 * cy**2) - (
            20 * 10**3 / 12 + 200 * (15 - cy) ** 2
        )
        iy = (80 * 100**3 / 12 + 8000 * cx**2) - (
            10 * 20**3 / 12 + 200 * (30 - cx) ** 2
        )
        ixy = 8000 * cx * cy - 200 * (30 - cx) * (15 - cy)
        assert_close(self, result.ix, ix)
        assert_close(self, result.iy, iy)
        assert_close(self, result.ixy, ixy)
        mean = (ix + iy) / 2
        radius = math.hypot((ix - iy) / 2, ixy)
        assert_close(self, result.imax, mean + radius)
        assert_close(self, result.imin, mean - radius)

    def test_translation_invariance(self):
        rects = [
            {"id": "a", "cx": 0, "cy": 0, "width": 60, "height": 40,
             "holes": [{"id": "h", "cx": 10, "cy": -5,
                        "width": 12, "height": 8}]},
            {"id": "b", "cx": 60, "cy": 30, "width": 20, "height": 100},
        ]
        base = load_sections(batch(make_section(rects)))[0]
        dx, dy = 137.5, -42.25
        shifted_rects = []
        for rect in rects:
            moved = dict(rect)
            moved["cx"] = rect["cx"] + dx
            moved["cy"] = rect["cy"] + dy
            if "holes" in rect:
                moved["holes"] = [
                    dict(h, cx=h["cx"] + dx, cy=h["cy"] + dy)
                    for h in rect["holes"]
                ]
            shifted_rects.append(moved)
        moved = load_sections(batch(make_section(shifted_rects)))[0]
        assert_close(self, moved.area, base.area)
        assert_close(self, moved.cx, base.cx + dx)
        assert_close(self, moved.cy, base.cy + dy)
        for name in ("ix", "iy", "ixy", "imax", "imin"):
            assert_close(self, getattr(moved, name), getattr(base, name))

    def test_component_contributions_sum_to_totals(self):
        result = load_sections(
            batch(make_section([
                {"id": "a", "cx": 0, "cy": 0, "width": 50, "height": 50,
                 "holes": [{"id": "h1", "cx": 10, "cy": 10,
                            "width": 10, "height": 10}]},
                {"id": "b", "cx": 50, "cy": 0, "width": 50, "height": 50},
            ]))
        )[0]
        for name in ("ix", "iy", "ixy"):
            total = sum(getattr(c, name) for c in result.components)
            assert_close(self, total, getattr(result, name))
        assert_close(
            self, sum(c.signed_area for c in result.components), result.area
        )
        kinds = [c.kind for c in result.components]
        self.assertEqual(kinds, ["solid", "hole", "solid"])
        hole = result.components[1]
        self.assertEqual(hole.parent_id, "a")
        self.assertLess(hole.signed_area, 0)

    def test_touching_solids_allowed(self):
        result = load_sections(
            batch(make_section([
                {"id": "a", "cx": 0, "cy": 0, "width": 10, "height": 10},
                {"id": "b", "cx": 10, "cy": 0, "width": 10, "height": 10},
            ]))
        )[0]
        assert_close(self, result.area, 200.0)


class ValidationTests(unittest.TestCase):
    def assert_invalid(self, text, *fragments):
        with self.assertRaises(SectionError) as ctx:
            load_sections(text)
        message = str(ctx.exception)
        for fragment in fragments:
            self.assertIn(fragment, message)

    def test_overlapping_solids_rejected(self):
        self.assert_invalid(
            batch(make_section([
                {"id": "a", "cx": 0, "cy": 0, "width": 10, "height": 10},
                {"id": "b", "cx": 5, "cy": 0, "width": 10, "height": 10},
            ])),
            "S1", "a", "b", "overlap",
        )

    def test_hole_outside_parent_rejected(self):
        self.assert_invalid(
            batch(make_section([
                {"id": "a", "cx": 0, "cy": 0, "width": 10, "height": 10,
                 "holes": [{"id": "h", "cx": 4, "cy": 0,
                            "width": 4, "height": 2}]},
            ])),
            "S1", "h", "a",
        )

    def test_overlapping_holes_rejected(self):
        self.assert_invalid(
            batch(make_section([
                {"id": "a", "cx": 0, "cy": 0, "width": 20, "height": 20,
                 "holes": [
                     {"id": "h1", "cx": 0, "cy": 0, "width": 6, "height": 6},
                     {"id": "h2", "cx": 2, "cy": 0, "width": 6, "height": 6},
                 ]},
            ])),
            "S1", "h1", "h2",
        )

    def test_duplicate_ids_rejected(self):
        self.assert_invalid(
            batch(make_section([
                {"id": "a", "cx": 0, "cy": 0, "width": 10, "height": 10},
                {"id": "a", "cx": 20, "cy": 0, "width": 10, "height": 10},
            ])),
            "duplicate",
        )
        self.assert_invalid(
            batch(
                make_section([{"id": "a", "cx": 0, "cy": 0,
                               "width": 1, "height": 1}], "S1"),
                make_section([{"id": "b", "cx": 0, "cy": 0,
                               "width": 1, "height": 1}], "S1"),
            ),
            "duplicate section",
        )

    def test_non_finite_and_non_positive_rejected(self):
        self.assert_invalid(
            batch(make_section([{"id": "a", "cx": 0, "cy": 0,
                                 "width": float("nan"), "height": 1}])),
            "finite",
        )
        self.assert_invalid(
            '{"sections": [{"id": "S1", "rectangles": ['
            '{"id": "a", "cx": 0, "cy": 0, "width": 1e999, "height": 1}]}]}',
            "finite",
        )
        self.assert_invalid(
            batch(make_section([{"id": "a", "cx": 0, "cy": 0,
                                 "width": -3, "height": 1}])),
            "positive",
        )

    def test_zero_effective_area_rejected(self):
        self.assert_invalid(
            batch(make_section([
                {"id": "a", "cx": 0, "cy": 0, "width": 10, "height": 10,
                 "holes": [{"id": "h", "cx": 0, "cy": 0,
                            "width": 10, "height": 10}]},
            ])),
            "effective area",
        )


class CliTests(unittest.TestCase):
    def run_cli(self, input_path, out_dir):
        return subprocess.run(
            [sys.executable, "-m", "section_props", str(input_path),
             "--out-dir", str(out_dir)],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )

    def test_cli_writes_csv_and_summary_sorted(self):
        sections = {
            "sections": [
                {"id": "B2", "rectangles": [
                    {"id": "r1", "cx": 0, "cy": 0, "width": 30, "height": 10},
                ]},
                {"id": "A1", "rectangles": [
                    {"id": "r1", "cx": 0, "cy": 0, "width": 10, "height": 10,
                     "holes": [{"id": "h1", "cx": 2, "cy": 1,
                                "width": 4, "height": 2}]},
                ]},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "in.json"
            out_path = Path(tmp) / "out"
            input_path.write_text(json.dumps(sections), encoding="utf-8")
            proc = self.run_cli(input_path, out_path)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            summary = json.loads(
                (out_path / "summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [s["id"] for s in summary["sections"]], ["A1", "B2"]
            )
            csv_text = (out_path / "A1.csv").read_text(encoding="utf-8")
            self.assertIn("h1", csv_text)
            self.assertIn("-8", csv_text)  # signed hole area

    def test_cli_failure_writes_nothing(self):
        bad = {"sections": [
            {"id": "ok", "rectangles": [
                {"id": "r1", "cx": 0, "cy": 0, "width": 5, "height": 5}]},
            {"id": "bad", "rectangles": [
                {"id": "r1", "cx": 0, "cy": 0, "width": 5, "height": 5},
                {"id": "r2", "cx": 1, "cy": 0, "width": 5, "height": 5}]},
        ]}
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "in.json"
            out_path = Path(tmp) / "out"
            input_path.write_text(json.dumps(bad), encoding="utf-8")
            proc = self.run_cli(input_path, out_path)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("bad", proc.stderr)
            self.assertIn("r1", proc.stderr)
            self.assertFalse(out_path.exists())


if __name__ == "__main__":
    unittest.main()
