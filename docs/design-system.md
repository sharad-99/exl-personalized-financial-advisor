# Design system: Evreghen Command Center

The frontend follows the "Evreghen Command Center" spec: a warm off-white workspace framed by a dark frosted
application shell, with orange as the single dominant accent for action, focus and telemetry.

## Where it lives

| Concern | File |
|---|---|
| Tokens (colours, radii, shadows, fonts, easing) | `frontend/src/app/globals.css` (`@theme`) and the `.shell-glass` utility |
| Shell (64px top bar, 256px sidebar, black 70% + 12px blur, white/10 borders) | `frontend/src/components/layout/app-shell.tsx` |
| Cards, buttons, status badges, notices, states, neutral table classes | `frontend/src/components/shared/ui.tsx` |
| Split login (white visualization half, orange half, white card) | `frontend/src/app/login/page.tsx` |
| Charts | `frontend/src/components/charts/*` |

Typography is the native system stack (`ui-sans-serif, system-ui, sans-serif`); no web font is loaded. The content
container is 1400px max with 32px horizontal padding.

## Deliberate deviations (accessibility)

| Spec | Measured | Implemented |
|---|---|---|
| White text on primary orange `#FE6E00` (buttons, active nav) | 2.82:1 (WCAG AA needs 4.5:1) | Text-bearing orange fills and orange text use `--color-primary-ink` **`#BE5200`**, the nearest shade of the same hue that passes (4.78:1 with white; 4.58:1 as text on `#FCFAF7`). The exact spec orange is kept for non-text signals: chart bars, focus ring, progress, accents, icons. |
| Success/danger colours as text | `#00C758` 2.16:1, `#FB2C36` 3.65:1 on the background | Text uses the spec's status foregrounds (`#016630`, `#874B00`) and a darkened danger ink `#C10007`; the bright semantic colours are used for icons and borders. |
| Text directly on the orange login panel | 2.86:1 | All login text sits inside the white card. |

To match the spec exactly at the cost of AA, set `--color-primary-ink: #fe6e00` in `globals.css`.

## Charts

- **Income vs expenses (two series):** info blue `#3080FF` and orange `#FE6E00` at full strength. Validated with
  the dataviz palette validator: colour-blind separation ΔE 31.2, normal-vision ΔE 39.4. At the spec's 60% chart
  opacity the pair fails the lightness band (too washed out to distinguish), so this chart is the one exception.
  A legend and a table view are always present.
- **Spending by category (single series):** orange at the spec's 60% fill opacity, with direct value labels and a
  table view.

## Status colours

| Meaning in this app | Spec status |
|---|---|
| Synthetic / demo data | Mock (pale yellow) |
| Neutral, dismissed, expired, low priority | Planned (soft grey) |
| Accepted / in progress, refunds | In development (pale blue) |
| High confidence, completed, on track | Production ready (pale green) |
| Pending recommendation | Orange tint (`primary/10`) |

Dark mode is not implemented; the spec anchors the identity in the light workspace.
