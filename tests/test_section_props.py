import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from section_props.geometry import Rect, compute_section
from section_props.validation import SectionError, parse_document

TOL = 1e-8


def close(actual, expected):
    return abs(actual - expected) <= TOL * max(1.0, abs(expected))


def doc(sections):
    return {"sections": sections}


def rect(rid, cx, cy, w, h, holes=None):
    r = {"id": rid, "cx": cx, "cy": cy, "width": w, "height": h}
    if holes:
        r["holes"] = holes
    return r


def hole(hid, cx, cy, w, h):
    return {"id": hid, "cx": cx, "cy": cy, "width": w, "height": h}


class GeometryTests(unittest.TestCase):
    def test_single_rect(self):
        res = compute_section("s", [Rect("r", 0.0, 0.0, 4.0, 6.0)], [])
        self.assertTrue(close(res.area, 24.0))
        self.assertTrue(close(res.centroid_x, 0.0))
        self.assertTrue(close(res.centroid_y, 0.0))
        self.assertTrue(close(res.ix, 4 * 6**3 / 12))
        self.assertTrue(close(res.iy, 6 * 4**3 / 12))
        self.assertTrue(close(res.ixy, 0.0))

    def test_eccentric_hole(self):
        # 100x80 solid at origin, 20x10 hole centred at (30, 20).
        solid = Rect("plate", 0.0, 0.0, 100.0, 80.0)
        h = Rect("h1", 30.0, 20.0, 20.0, 10.0, sign=-1)
        res = compute_section("s", [solid], [("plate", h)])
        area = 100 * 80 - 20 * 10
        gx = (0 - 200 * 30) / area
        gy = (0 - 200 * 20) / area
        self.assertTrue(close(res.area, area))
        self.assertTrue(close(res.centroid_x, gx))
        self.assertTrue(close(res.centroid_y, gy))
        ix = 100 * 80**3 / 12 + 8000 * gy**2
        ix -= 20 * 10**3 / 12 + 200 * (20 - gy) ** 2
        iy = 80 * 100**3 / 12 + 8000 * gx**2
        iy -= 10 * 20**3 / 12 + 200 * (30 - gx) ** 2
        ixy = 8000 * gx * gy - 200 * (30 - gx) * (20 - gy)
        self.assertTrue(close(res.ix, ix))
        self.assertTrue(close(res.iy, iy))
        self.assertTrue(close(res.ixy, ixy))
        # Contributions sum to totals.
        self.assertTrue(close(sum(c.ix for c in res.contributions), res.ix))
        self.assertTrue(close(sum(c.iy for c in res.contributions), res.iy))
        self.assertTrue(close(sum(c.ixy for c in res.contributions), res.ixy))
        self.assertTrue(close(sum(c.signed_area for c in res.contributions), res.area))
        # Principal moments bracket both centroidal moments here.
        self.assertGreaterEqual(res.imax, max(res.ix, res.iy) - 1e-6)
        self.assertLessEqual(res.imin, min(res.ix, res.iy) + 1e-6)

    def test_translation_invariance(self):
        solids = [Rect("a", 0.0, 0.0, 10.0, 4.0), Rect("b", 8.0, 5.0, 3.0, 6.0)]
        holes = [("b", Rect("h", 9.0, 6.0, 1.0, 2.0, sign=-1))]
        base = compute_section("s", solids, holes)
        dx, dy = 137.5, -42.25
        moved_solids = [
            Rect(r.rect_id, r.cx + dx, r.cy + dy, r.width, r.height) for r in solids
        ]
        moved_holes = [
            (p, Rect(h.rect_id, h.cx + dx, h.cy + dy, h.width, h.height, sign=-1))
            for p, h in holes
        ]
        moved = compute_section("s", moved_solids, moved_holes)
        self.assertTrue(close(moved.area, base.area))
        self.assertTrue(close(moved.centroid_x, base.centroid_x + dx))
        self.assertTrue(close(moved.centroid_y, base.centroid_y + dy))
        for name in ("ix", "iy", "ixy", "imax", "imin"):
            self.assertTrue(close(getattr(moved, name), getattr(base, name)))

    def test_principal_moments_known_shape(self):
        # Symmetric built-up section; principal values match the formula.
        solids = [
            Rect("top", 0.0, 4.0, 10.0, 2.0),
            Rect("web", 0.0, 0.0, 2.0, 6.0),
            Rect("bot", 0.0, -4.0, 10.0, 2.0),
        ]
        res = compute_section("s", solids, [])
        avg = (res.ix + res.iy) / 2
        radius = (((res.ix - res.iy) / 2) ** 2 + res.ixy**2) ** 0.5
        self.assertTrue(close(res.imax, avg + radius))
        self.assertTrue(close(res.imin, avg - radius))


class ValidationTests(unittest.TestCase):
    def test_valid_document(self):
        data = doc(
            [
                {
                    "id": "S1",
                    "rectangles": [
                        rect("r1", 0, 0, 10, 10, holes=[hole("h1", 2, 2, 2, 2)])
                    ],
                }
            ]
        )
        sections = parse_document(data)
        self.assertEqual(len(sections), 1)

    def test_duplicate_section_id(self):
        data = doc(
            [
                {"id": "S1", "rectangles": [rect("a", 0, 0, 1, 1)]},
                {"id": "S1", "rectangles": [rect("b", 0, 0, 1, 1)]},
            ]
        )
        with self.assertRaisesRegex(SectionError, "S1"):
            parse_document(data)

    def test_duplicate_rect_id(self):
        data = doc(
            [
                {
                    "id": "S1",
                    "rectangles": [rect("a", 0, 0, 1, 1), rect("a", 5, 5, 1, 1)],
                }
            ]
        )
        with self.assertRaisesRegex(SectionError, "S1.*'a'"):
            parse_document(data)

    def test_non_finite_value(self):
        data = doc([{"id": "S1", "rectangles": [rect("a", 0, 0, 1, float("nan"))]}])
        with self.assertRaisesRegex(SectionError, "S1.*'a'"):
            parse_document(data)

    def test_non_positive_width(self):
        data = doc([{"id": "S1", "rectangles": [rect("a", 0, 0, -1, 1)]}])
        with self.assertRaisesRegex(SectionError, "width"):
            parse_document(data)

    def test_solid_overlap_rejected_but_touching_ok(self):
        bad = doc(
            [
                {
                    "id": "S1",
                    "rectangles": [rect("a", 0, 0, 2, 2), rect("b", 1, 0, 2, 2)],
                }
            ]
        )
        with self.assertRaisesRegex(SectionError, "overlap"):
            parse_document(bad)
        ok = doc(
            [
                {
                    "id": "S1",
                    "rectangles": [rect("a", 0, 0, 2, 2), rect("b", 2, 0, 2, 2)],
                }
            ]
        )
        parse_document(ok)

    def test_hole_must_be_inside_parent(self):
        data = doc(
            [
                {
                    "id": "S1",
                    "rectangles": [rect("a", 0, 0, 4, 4, holes=[hole("h", 3, 0, 4, 1)])],
                }
            ]
        )
        with self.assertRaisesRegex(SectionError, "S1.*'h'"):
            parse_document(data)

    def test_hole_overlap_rejected_but_touching_ok(self):
        bad = doc(
            [
                {
                    "id": "S1",
                    "rectangles": [
                        rect(
                            "a",
                            0,
                            0,
                            10,
                            10,
                            holes=[hole("h1", -1, 0, 2, 2), hole("h2", 0, 0, 2, 2)],
                        )
                    ],
                }
            ]
        )
        with self.assertRaisesRegex(SectionError, "overlap"):
            parse_document(bad)
        ok = doc(
            [
                {
                    "id": "S1",
                    "rectangles": [
                        rect(
                            "a",
                            0,
                            0,
                            10,
                            10,
                            holes=[hole("h1", -2, 0, 2, 2), hole("h2", 0, 0, 2, 2)],
                        )
                    ],
                }
            ]
        )
        parse_document(ok)

    def test_non_positive_net_area(self):
        data = doc(
            [
                {
                    "id": "S1",
                    "rectangles": [rect("a", 0, 0, 2, 2, holes=[hole("h", 0, 0, 2, 2)])],
                }
            ]
        )
        with self.assertRaisesRegex(SectionError, "area"):
            parse_document(data)


class CliTests(unittest.TestCase):
    def _run_cli(self, tmp, payload):
        src = Path(tmp) / "in.json"
        src.write_text(json.dumps(payload), encoding="utf-8")
        outdir = Path(tmp) / "out"
        proc = subprocess.run(
            [sys.executable, "-m", "section_props", str(src), str(outdir)],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
        )
        return proc, outdir

    def test_cli_outputs_and_stable_order(self):
        payload = doc(
            [
                {"id": "B", "rectangles": [rect("r1", 0, 0, 4, 4)]},
                {
                    "id": "A",
                    "rectangles": [
                        rect("r2", 0, 0, 10, 10, holes=[hole("h1", 3, 3, 2, 2)])
                    ],
                },
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            proc, outdir = self._run_cli(tmp, payload)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            summary = json.loads((outdir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual([s["id"] for s in summary["sections"]], ["A", "B"])
            sec_a = summary["sections"][0]
            self.assertTrue(close(sec_a["area_mm2"], 96.0))
            # CSV rows sorted by rect id, contributions sum to summary.
            with open(outdir / "A.csv", newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual([r["rect_id"] for r in rows], ["h1", "r2"])
            self.assertEqual(rows[0]["parent_id"], "r2")
            self.assertEqual(rows[1]["parent_id"], "")
            self.assertTrue(
                close(sum(float(r["signed_area_mm2"]) for r in rows), 96.0)
            )
            self.assertTrue(
                close(sum(float(r["ix_mm4"]) for r in rows), sec_a["ix_mm4"])
            )

    def test_cli_invalid_batch_writes_nothing(self):
        payload = doc(
            [
                {"id": "ok", "rectangles": [rect("r1", 0, 0, 4, 4)]},
                {"id": "bad", "rectangles": [rect("r2", 0, 0, -1, 4)]},
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            proc, outdir = self._run_cli(tmp, payload)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("bad", proc.stderr)
            self.assertIn("r2", proc.stderr)
            self.assertFalse(outdir.exists() and any(outdir.iterdir()))


if __name__ == "__main__":
    unittest.main()
