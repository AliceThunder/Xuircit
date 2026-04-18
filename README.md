# Xuircit

A desktop GUI application for drawing electrical, electronic, and power electronics circuit schematics.

## Features

- **Visual drag-and-drop drawing** — pick components from a categorized palette and place them on a zoomable, pannable canvas
- **SPICE netlist mode** — write or import standard SPICE netlists; sync the canvas and netlist bidirectionally
- **Full component library** — Resistors, Capacitors, Inductors, Transformers, Voltage/Current Sources, Dependent Sources (VCVS/CCCS/VCCS/CCVS), Diodes, Zener Diodes, BJTs (NPN/PNP), MOSFETs (N/P), IGBTs, Ideal Switches, SCRs, TRIACs, Ground, Net Labels, Junctions
- **Export** — PNG, SVG, PDF schematic images; `.sp`/`.net` SPICE netlist files
- **Save/load** — `.xcit` JSON project format (human-readable, version-control friendly)

## Requirements

- Python 3.10+
- PyQt6 ≥ 6.4.0

## Installation

```bash
pip install -r requirements.txt
```

## Running

```bash
python src/main.py
```

## Project Structure

```
src/
  main.py                     # Entry point
  app/main_window.py          # Main window, menus, toolbars, status bar
  canvas/                     # QGraphicsScene/View canvas with zoom/pan/grid
  components/                 # Schematic symbol graphics items (QPainterPath)
  panels/                     # Palette, properties, and netlist editor docks
  dialogs/                    # Export and import dialogs
  io/                         # File I/O, SPICE parser/generator, SVG/PNG/PDF export
  models/                     # Circuit data model and component library registry
```

## Usage

### Drawing mode

1. Select a component from the **left palette** (double-click or press **Place Selected**)
2. Click on the canvas to place it; right-click to cancel
3. Press **W** or choose **Tools → Draw Wire** to connect pins
4. Hover over a component to reveal its pin dots (blue), click a pin to start a wire, click again to finish
5. Right-click a component for **Rotate CW / CCW**, **Properties…**, **Delete**

### Netlist mode

1. Open the **Netlist Editor** dock at the bottom
2. Click **Generate from Schematic** to produce a SPICE netlist from the canvas
3. Edit the netlist directly, then click **Apply to Schematic** to rebuild the canvas

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Escape` | Switch to Select mode |
| `W` | Switch to Wire-drawing mode |
| `Del` / `Backspace` | Delete selected items |
| `Ctrl+N` | New schematic |
| `Ctrl+O` | Open project |
| `Ctrl+S` | Save project |
| `Ctrl+Z` / `Ctrl+Y` | Undo / Redo |
| `Ctrl++` / `Ctrl+-` | Zoom in / out |
| `Ctrl+0` | Fit all in view |
| `Ctrl+Scroll` | Zoom in/out |
| Middle-mouse drag | Pan canvas |

## Component Library

| Category | Components |
|----------|------------|
| Passive | Resistor (R), Capacitor (C), Inductor (L), Transformer (T) |
| Sources | Voltage (V), Current (I), VCVS (E), CCCS (F), VCCS (G), CCVS (H) |
| Semiconductors | Diode (D), Zener (Z), NPN/PNP BJT (Q), NMOS/PMOS FET (M), IGBT |
| Power Electronics | Ideal Switch (SW), SCR, TRIAC |
| Wiring | Ground (GND), Net Label, Junction |

## File Formats

- **`.xcit`** — JSON project file (positions, values, connections, metadata)
- **`.sp` / `.net` / `.cir`** — SPICE netlist (compatible with LTspice, Ngspice, HSPICE)
- **`.png` / `.svg` / `.pdf`** — Exported schematic image