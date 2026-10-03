# Composite Section Properties

Compute geometric properties of composite cross-sections built from
axis-aligned solid rectangles with rectangular holes. Pure standard
library, no plotting. All lengths are in millimetres.

## Usage

```
python -m section_props INPUT_JSON OUTPUT_DIR
```

The whole batch is validated first: if any section is invalid, the
command exits non-zero, prints an error locating the section and
rectangle, and writes no output files.

## Input format

```json
{
  "sections": [
    {
      "id": "S1",
      "rectangles": [
        {
          "id": "plate",
          "cx": 0.0, "cy": 0.0, "width": 100.0, "height": 80.0,
          "holes": [
            {"id": "h1", "cx": 30.0, "cy": 20.0, "width": 20.0, "height": 10.0}
          ]
        }
      ]
    }
  ]
}
```

- `cx`, `cy`: centre coordinates (mm); `width` (x extent) and `height`
  (y extent) must be positive; every number must be finite.
- Section ids are unique; rectangle/hole ids are unique within a section.
- Solid rectangles must not overlap (boundary contact is allowed).
- Each hole belongs to its parent solid, must lie fully inside it
  (boundary contact allowed), and holes of one solid must not overlap.
- The net effective area of every section must be positive.

## Output

Written into `OUTPUT_DIR`, ordered by section id:

- `summary.json`: per-section effective area (mm^2), centroid (mm),
  centroidal second moments of area `ix_mm4`, `iy_mm4`, product of
  inertia `ixy_mm4` (integral of x*y dA about the centroid), and
  principal moments `imax_mm4` / `imin_mm4` (mm^4).
- `<section_id>.csv`: one row per constituent rectangle (holes have
  negative signed area) with its signed area and its contribution to
  `Ix`, `Iy`, `Ixy`, including the parallel-axis transfer to the global
  centroid. Contributions sum to the summary values.

These are second moments of area (mm^4), not mass moments of inertia.

## Method

Signed areas: solids add, holes subtract. The centroid is the
signed-area-weighted mean. Each rectangle contributes its own centroidal
second moment (`b*h^3/12`, `h*b^3/12`) plus the parallel-axis transfer
`A*d^2` (and `A*dx*dy` for the product of inertia) to the global
centroid; holes subtract both terms. Principal moments follow from
`(Ix+Iy)/2 ± sqrt(((Ix-Iy)/2)^2 + Ixy^2)`.

## Tests

```
python -m unittest discover -s tests -v
```
