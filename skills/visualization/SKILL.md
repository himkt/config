---
name: visualization
description: Use this skill whenever you are about to create ANY chart, graph, plot, dashboard, or data visualization, in ANY output medium — an HTML page, inline SVG, or plotting code in any library (matplotlib, plotly, d3, Recharts, …). Read it BEFORE writing the first line of chart code, choosing chart colors, building a stat tile / meter / KPI row, or laying out a dashboard. Triggers on "chart", "graph", "plot", "data viz", "visualization", "dashboard", "analytics", "visualize data", "stat tile", "sparkline", "heatmap", "legend", "axis", "tooltip", "chart colors".
---

# Data Visualization

A chart is **read by people and executed by you**. This skill turns "make it look
good" into a procedure with checks, so the result is right by construction rather
than by taste. The method is design-system-agnostic: a brand supplies palette
*parameters*; the procedure and rules stay fixed.

## Always render as SVG

Every data visualization is rendered as **SVG** — inline `<svg>` markup in an HTML
page, or a standalone `.svg` file. This is a hard requirement:

- Hand-written charts: author the marks directly as SVG elements.
- Plotting libraries: configure SVG output explicitly — matplotlib
  `savefig("chart.svg")`, plotly `fig.write_image("chart.svg")`, d3 and
  Recharts render SVG by default.
- `<canvas>` rendering and raster images (PNG/JPEG) are forbidden as the
  delivered artifact. A raster screenshot is acceptable only as a verification
  aid in step 7, never as the deliverable.

SVG keeps text selectable, scales cleanly at any zoom, and lets the hover layer,
dark mode, and texture fills attach to real DOM nodes.

## The procedure — do these in order

Color comes LAST. Most bad charts pick colors first.

1. **Pick the form.** What is the data's job — magnitude, identity, polarity, a
   single headline, change-over-time? The job picks the chart type, and sometimes
   the answer is *not a chart* (a stat tile or hero number). Bars for magnitude
   comparison, lines for change-over-time, scatter for correlation, heatmap for
   density over two dimensions. Never pie charts beyond 2–3 slices.
2. **Assign color by the job it does.** Categorical (identity), sequential
   (magnitude), diverging (polarity), or status (state) — each has one rule.
   Assign categorical hues in fixed slot order, never cycled.
3. **Validate the palette — compute, don't eyeball.** The default palette below is
   pre-validated. When substituting brand colors, verify programmatically (write a
   short script; OKLab ΔE ×100): adjacent-pair separation under CVD simulation
   (deuteranopia/protanopia/tritanopia) ΔE ≥ 8; normal-vision adjacent-pair
   ΔE ≥ 15 (hard floor); contrast vs the chart surface ≥ 3:1 (below that, ship
   visible direct labels or a table view). Validate light and dark modes
   separately, each against its own surface.
4. **Apply mark specs & spacers.** Thin marks; 4px rounded data-ends anchored to
   the baseline; 2px lines; ≥8px markers; a 2px surface-color gap between fills
   (stacked segments and adjacent bars alike) and a 2px surface ring on
   overlapping marks; selective direct labels (never a number on every point).
5. **Add the hover layer — by default.** An SVG chart *is* interactive: crosshair
   + tooltip on line/area, per-mark hover tooltip on bar/dot/cell. Only a bare
   stat tile with no plot skips it. Hit targets bigger than the mark; filters in
   one row above the charts.
6. **Final accessibility pass.** For ≥ 2 series a legend is always present and
   ≤ 4 series are also direct-labeled (a single series needs no legend — the
   title names it), so identity is never color-alone. A table view exists. Dark
   mode is **selected** — its own steps from the same hue ramps, validated
   against the dark surface, never an automatic flip. A 45°/135° line-texture
   fill is available for the CVD/print/forced-colors case.
7. **Render it and look at it.** Validation checks color, not layout — open or
   screenshot the output and eyeball it for label collisions, geometry, and
   overflow before calling it done.

## Non-negotiables

- **Every visualization is SVG** — see above.
- **Assign categorical hues in fixed slot order, never cycled.** A 9th series is
  never a generated hue — fold it into "Other," small multiples, or composite
  encoding.
- **One axis.** Never a dual-axis chart (two y-scales). Two measures of different
  scale → two charts, small multiples, or index both to a common base. This is
  the #1 chart mistake.
- **Color follows the entity, never its rank.** A filter that changes the series
  count must not repaint the survivors.
- **Sequential = one hue, light→dark. Diverging = two hues + a neutral gray
  midpoint.** Never a rainbow; never a hue at the diverging midpoint.
- **Text wears text tokens, never the series color** — values, labels, and
  legends stay in primary/secondary/muted ink; a colored mark beside them
  carries identity.
- **Status colors are reserved** (good/warning/serious/critical) and never reused
  as series colors; they ship with an icon + label, never color alone.
- **Recessive chrome.** Hairline gridlines, muted axis labels, no chart borders,
  no drop shadows, no 3D.

## Default palette (pre-validated)

Define slots as CSS custom properties in a local `<style>` block and write the
chart body against roles, not raw hex. Declare dark values under both
`prefers-color-scheme: dark` and a `[data-theme="dark"]` scope.

### Categorical (identity) — use in this order, stop at what you need

| Slot | Hue | Light | Dark |
|------|-----|-------|------|
| 1 | blue | `#2a78d6` | `#3987e5` |
| 2 | orange | `#eb6834` | `#d95926` |
| 3 | aqua | `#1baf7a` | `#199e70` |
| 4 | yellow | `#eda100` | `#c98500` |
| 5 | magenta | `#e87ba4` | `#d55181` |
| 6 | green | `#008300` | `#008300` |
| 7 | violet | `#4a3aa7` | `#9085e9` |
| 8 | red | `#e34948` | `#e66767` |

The order is the CVD-safety mechanism, not cosmetic. For chart forms where every
pair can sit adjacent (scatter, bubble, choropleth, small multiples), only the
first **three** slots are safe together — past three, fold to "Other" or facet.

### Sequential (magnitude) — single blue ramp, light→dark

`#cde2fb` → `#9ec5f4` → `#6da7ec` → `#3987e5` → `#256abf` → `#184f95` → `#0d366b`

A second simultaneous sequential context takes orange as its own one-hue ramp.
For discrete ordinal marks (funnel stages, tiers), the step nearest the surface
must still clear 2:1 contrast.

### Diverging (polarity)

blue ↔ red poles, neutral gray midpoint (light `#f0efec`, dark `#383835`),
equal step count per arm.

### Status (state) — fixed, never themed

| Role | Hex |
|---|---|
| good | `#0ca30c` |
| warning | `#fab219` |
| serious | `#ec835a` |
| critical | `#d03b3b` |

Always icon + label alongside the color.

### Surfaces & ink

| Role | Light | Dark |
|---|---|---|
| Chart surface | `#fcfcfb` | `#1a1a19` |
| Primary ink | `#0b0b0b` | `#ffffff` |
| Secondary ink | `#52514e` | `#c3c2b7` |
| Muted (axis/labels) | `#898781` | `#898781` |
| Gridline (hairline) | `#e1e0d9` | `#2c2c2a` |
| Baseline / axis | `#c3c2b7` | `#383835` |

Typeface: the system UI sans everywhere, including hero figures; reserve
`font-variant-numeric: tabular-nums` for columns that must align (tables, axis
ticks).

## Anti-pattern checklist — if your chart matches one, it's wrong

- Dual y-axes
- Rainbow or cycled palettes; hue generated for extra series
- Pie/donut with more than 3 slices
- A number printed on every data point
- Legend colors as the only way to identify a series
- Text in the series color
- Truncated bar-chart baselines (bars must start at zero)
- 3D, drop shadows, gradient fills for decoration
- Dark mode produced by inverting/auto-flipping the light palette
- Status colors used as ordinary series colors
- Canvas or raster output instead of SVG
