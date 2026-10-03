# Composite Section Properties

Computes geometric properties of composite cross-sections built from
axis-aligned solid rectangles with rectangular holes. Standard library
only; no plotting. All lengths are in millimetres, areas in mm² and
second moments of area in mm⁴.

## Usage

```
python -m section_props INPUT.json --out-dir OUT_DIR
```

The whole batch is validated and computed before anything is written:
if any section is invalid the command exits non-zero, prints an error
locating the section and rectangle, and creates no output files.

## Input format

```json
{
  "sections": [
    {
      "id": "S1",
      "rectangles": [
        {"id": "web", "cx": 0, "cy": 0, "width": 20, "height": 100},
        {"id": "flange", "cx": 0, "cy": 60, "width": 80, "height": 20,
         "holes": [
           {"id": "bolt", "cx": 10, "cy": 60, "width": 8, "height": 8}
         ]}
      ]
    }
  ]
}
```

Rules enforced per batch:

- Section ids are unique; rectangle ids (solids and holes) are unique
  within a section.
- `cx`, `cy`, `width`, `height` must be finite numbers; width and
  height must be positive.
- Solid rectangle interiors must not overlap (boundary contact is
  allowed).
- Each hole belongs to the solid rectangle whose `holes` list contains
  it and must lie fully inside that solid's boundary; holes of the same
  solid must not overlap.
- The total effective area (solids minus holes) must be positive.

## Method

- Effective area: solid areas are added, hole areas subtracted; the
  centroid uses signed areas (`cx = Σ Aᵢ·xᵢ / Σ Aᵢ`).
- Second moments of area `Ix = ∫ y² dA` and `Iy = ∫ x² dA` are taken
  about centroidal axes parallel to the global axes; the product of
  inertia is `Ixy = ∫ x·y dA` in centroidal coordinates. These are
  area (not mass) moments of inertia.
- Each rectangle contributes its own centroidal moment (`b·h³/12`)
  plus the parallel-axis transfer term; holes subtract both terms.
- Principal moments `Imax`/`Imin` come from
  `(Ix+Iy)/2 ± √(((Ix−Iy)/2)² + Ixy²)`; principal directions are not
  reported.

## Output

Written to `--out-dir`, ordered by section id for stable output:

- `summary.json` — per section: area (mm²), centroid (mm), `ix_mm4`,
  `iy_mm4`, `ixy_mm4`, `imax_mm4`, `imin_mm4`.
- `<section-id>.csv` — one row per component rectangle with its signed
  area (mm²), centre, and its contributions to `Ix`, `Iy`, `Ixy` (mm⁴).
  The signed contributions sum to the totals in `summary.json`.

## Tests

```
python -m unittest discover -s tests -v
```

Covers eccentric holes, translation invariance of the inertia terms,
component/total consistency, validation failures, and CLI behaviour.
