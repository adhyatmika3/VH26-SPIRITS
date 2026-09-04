---
name: Alert Fatigue Buster
colors:
  surface: '#f7f9fb'
  surface-dim: '#d8dadc'
  surface-bright: '#f7f9fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f4f6'
  surface-container: '#eceef0'
  surface-container-high: '#e6e8ea'
  surface-container-highest: '#e0e3e5'
  on-surface: '#191c1e'
  on-surface-variant: '#464555'
  inverse-surface: '#2d3133'
  inverse-on-surface: '#eff1f3'
  outline: '#777587'
  outline-variant: '#c7c4d8'
  surface-tint: '#4d44e3'
  primary: '#3525cd'
  on-primary: '#ffffff'
  primary-container: '#4f46e5'
  on-primary-container: '#dad7ff'
  inverse-primary: '#c3c0ff'
  secondary: '#565e74'
  on-secondary: '#ffffff'
  secondary-container: '#dae2fd'
  on-secondary-container: '#5c647a'
  tertiary: '#004c76'
  on-tertiary: '#ffffff'
  tertiary-container: '#00659a'
  on-tertiary-container: '#bedfff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e2dfff'
  primary-fixed-dim: '#c3c0ff'
  on-primary-fixed: '#0f0069'
  on-primary-fixed-variant: '#3323cc'
  secondary-fixed: '#dae2fd'
  secondary-fixed-dim: '#bec6e0'
  on-secondary-fixed: '#131b2e'
  on-secondary-fixed-variant: '#3f465c'
  tertiary-fixed: '#cce5ff'
  tertiary-fixed-dim: '#93ccff'
  on-tertiary-fixed: '#001d31'
  on-tertiary-fixed-variant: '#004b73'
  background: '#f7f9fb'
  on-background: '#191c1e'
  surface-variant: '#e0e3e5'
typography:
  display:
    fontFamily: Geist
    fontSize: 36px
    fontWeight: '600'
    lineHeight: 44px
    letterSpacing: -0.025em
  display-mobile:
    fontFamily: Geist
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-sm:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.015em
  body-lg:
    fontFamily: Geist
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
    letterSpacing: -0.01em
  body-md:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0em
  body-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0em
  label-md:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Geist
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.02em
  code-lg:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: -0.01em
  code-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0em
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 14px
    letterSpacing: 0em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  space-2xs: 0.125rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-base: 1rem
  space-lg: 1.25rem
  space-xl: 1.5rem
  space-2xl: 2rem
  gutter-compact: 0.75rem
  gutter-normal: 1rem
  gutter-loose: 1.5rem
---

## Brand & Style

This design system targets Site Reliability Engineers, DevOps teams, and on-call responders who operate under intense cognitive load during system incidents. The interface prioritizes rapid pattern recognition, precise signal extraction, and decisive action over decorative visual treatments. 

The aesthetic is precision-engineered minimalism: clinical, hyper-legible, quiet, and utilitarian. It deliberately reduces ambient visual noise so that telemetry data, alert clusters, correlated root causes, and severity states communicate instantaneously. High-density data tables and incident graphs exist comfortably alongside generous whitespace, establishing an authoritative environment that counters stress with calm technical precision.

## Colors

The palette establishes an ultra-clean, functional canvas using slate and zinc neutrals paired with a high-contrast charcoal text hierarchy. Semantics are uncompromisingly clear, mapped strictly to incident severity states and operational telemetry.

### Palette Architecture
- **Surfaces & Grounds**: Base viewport canvas uses `#f8fafc`. Content cards, elevated panels, flyovers, and active table rows use `#ffffff`. Structural boundaries are delineated by neutral strokes in `#e2e8f0` (subtle) and `#cbd5e1` (strong/hover).
- **Text & Hierarchy**:
  - Primary text: `#0f172a` (high-contrast charcoal for logs, metric values, and headers).
  - Secondary text: `#475569` (supporting metadata, labels, and timestamps).
  - Muted text: `#94a3b8` (disabled states, subtle hints, empty states).
- **Brand Accent**: Deep Indigo / Cobalt (`#4f46e5`) reserved for system-level actions, primary navigation states, active grouping toggles, and primary callouts.

### Incident Severity & Status Semantics
Each operational status level possesses a coordinated triple (foreground, background, border) engineered to maintain legibility and avoid color vibration:
- **Critical (P0/P1)**: Text/Icon `#ef4444`, Background `#fef2f2`, Border `#fecaca`.
- **High (P2)**: Text/Icon `#f97316`, Background `#fff7ed`, Border `#ffedd5`.
- **Medium / Warning (P3)**: Text/Icon `#d97706`, Background `#fffbeb`, Border `#fef3c7`.
- **Healthy / Resolved**: Text/Icon `#059669`, Background `#ecfdf5`, Border `#a7f3d0`.
- **Info / Low (P4)**: Text/Icon `#0284c7`, Background `#f0f9ff`, Border `#bae6fd`.

## Typography

The typography structure splits responsibilities between a clean grotesque sans-serif (`Geist`) and a monospaced companion (`JetBrains Mono`). 

### Type Application Rules
- **Structural Text**: Use `Geist` for views, page titles, triage summaries, metric documentation, and prose incident reports. Tight tracking (-0.02em to -0.01em) ensures optical stability in dense tabular views.
- **Machine Data & Observability Telemetry**: Use `JetBrains Mono` exclusively for telemetry outputs, including alert fingerprints, commit SHAs, trace IDs, PromQL/LogQL queries, raw logs, numerical anomaly scores, IP addresses, and ISO timestamps.
- **Tabular Figures**: Tabular numeral alignment (`font-variant-numeric: tabular-nums`) must be enabled across all body and monospaced styles to prevent vertical jitter during real-time metric updates.

## Layout & Spacing

This design system uses an adaptable fluid grid with fixed boundary containers, optimized for high-density multi-panel triage screens, multi-monitor incident operations centers (NOCs), and responsive mobile on-call escalation views.

### Screen Layout & Breakpoints
- **Desktop (>= 1280px)**: Multi-pane layout. 240px collapsable navigation rail, dynamic 3-column triage pane (Alert Groups, Correlated Timeline, Deep Telemetry / Runbooks) with `gutter-normal` (16px) spacing.
- **Tablet / Small Desktop (768px - 1279px)**: Collapsible sidebar, 2-column layout (Alert Stream + Selected Detail drawer) using `gutter-compact` (12px).
- **Mobile (< 768px)**: Stacked single-column card layout. Global search and critical alert counts collapse into a sticky top incident banner.

### Spacing Principles
All element positioning conforms strictly to a 4px baseline. Form fields and table cells favor compact internal paddings (6px–8px vertical, 10px–12px horizontal) to maximize vertical information scanning efficiency.

## Elevation & Depth

Visual depth is achieved primarily through layered neutral surfaces and sharp low-contrast outlines rather than heavy diffuse drop shadows. This preserves high signal contrast on display screens.

### Layer Hierarchy
- **Base Canvas (Level 0)**: `#f8fafc`. Background on which all structural layouts reside.
- **Card / Surface Container (Level 1)**: `#ffffff` bounded by an explicit 1px stroke of `#e2e8f0`. No drop shadow.
- **Interactive Hover & Group Focus (Level 2)**: `#ffffff` with a subtle elevation shadow: `0 1px 3px 0 rgba(15, 23, 42, 0.06), 0 1px 2px -1px rgba(15, 23, 42, 0.04)` and border shifted to `#cbd5e1`.
- **Flyouts, Dropdowns & Modals (Level 3)**: `#ffffff` bounded by `#cbd5e1`, with structured shadow: `0 4px 6px -1px rgba(15, 23, 42, 0.08), 0 2px 4px -2px rgba(15, 23, 42, 0.05)`.
- **Critical Interruption / Sticky Triage Overlays (Level 4)**: High-priority banners use semantic tint backgrounds (`#fef2f2`) pinned with a 1px border (`#fecaca`) and soft downward ambient occlusion: `0 10px 15px -3px rgba(15, 23, 42, 0.08)`.

## Shapes

The design system implements a controlled corner radius of 4px (`rounded-sm`) to 6px (`rounded-md`), delivering a compact, industrial engineering instrument feel.

### Geometric Rules
- **Micro Elements & Tags**: Badges, status chips, severity pills, and monospaced metric indicators use `4px` (`rounded-sm`).
- **Form Controls & Triggers**: Text fields, select inputs, action buttons, and segmented controls use `6px` (`rounded-md`).
- **Panels & Modules**: Cards, triage containers, log viewers, and floating popovers use `6px` (`rounded-md`).
- **Full Radius (Pill)**: Reserved solely for circular avatar indicators and pulse status dots (e.g., active telemetry pulsing dot).

## Components

### Buttons
- **Primary**: Background `#4f46e5`, text `#ffffff`, hover `#4338ca`, active `#3730a3`. Corner radius 6px. Height 32px (compact) or 36px (default). Typography: `label-md`.
- **Secondary / Outline**: Background `#ffffff`, border 1px `#e2e8f0`, text `#0f172a`, hover border `#cbd5e1`, hover background `#f8fafc`.
- **Destructive / Acknowledge Urgent**: Background `#ef4444`, text `#ffffff`, hover `#dc2626`.
- **Ghost / Icon Button**: Transparent background, text `#475569`, hover background `#f1f5f9`, hover text `#0f172a`.

### Status Badges & Severity Chips
- Displayed with typography `code-sm` or `label-sm` with a fixed height of 22px, padding `2px 8px`, and radius of 4px.
- Use the semantic triples defined in the color section (e.g., Critical alerts render with `#fef2f2` background, `#fecaca` border, and `#ef4444` bold text).
- Include an optional 6px circular indicator dot on the leading edge matching the text token.

### Cards & Grouped Triage Panels
- Surface `#ffffff`, border 1px `#e2e8f0`, radius 6px. Padding ranges from 12px (log/dense views) to 16px (standard metric cards).
- **Correlation Clusters**: When an alert group collapses 20+ alerts into a single incident card, use a 2px left accent border corresponding to the highest child severity level (e.g., solid `#ef4444` border-left for critical groups).

### Input Fields & Search Bars
- Background `#ffffff`, border 1px `#cbd5e1`, radius 6px, text `#0f172a`, placeholder text `#94a3b8`.
- Focus state: Border `#4f46e5` with a 1px ambient outline ring: `box-shadow: 0 0 0 1px #4f46e5`.
- Filter inputs (PromQL/Regex queries) render in `code-md` (`JetBrains Mono`).

### Checkboxes & Radio Controls
- Base: 16x16px square (checkbox) or circle (radio), border 1px `#cbd5e1`, radius 4px (checkbox).
- Checked: Background `#4f46e5`, border `#4f46e5`, white checkmark or center pip icon.

### Telemetry Stream & Log Tables
- Striped or bordered rows: Row height fixed to 28px (ultra-dense) or 34px (standard).
- Alternating subtle row backgrounds on `#ffffff` with hover state `#f8fafc`.
- Border-bottom 1px `#f1f5f9`. Headers in `label-sm` uppercase with text `#475569` and background `#f8fafc`.

### Fingerprint & Hash Blocks
- Inline code tags: Background `#f1f5f9`, border 1px `#e2e8f0`, text `#0f172a`, radius 4px, font `code-sm`, padding `1px 4px`.