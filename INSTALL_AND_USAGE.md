# INSTALL_AND_USAGE

## Feature Recap

This tool lets you:

- Load a batch of photos and switch between them via thumbnails.
- Generate thumbnails in the background so loading a batch stays responsive.
- Apply embedded photo orientation consistently in the preview and printed output.
- Preview paper size, print area, and fit mode before printing.
- Choose global fit behavior and override it per photo.
- Choose color depth or grayscale/black-and-white output, with optional dithering and per-photo overrides.
- Add inch or percentage margins inside the selected print size for bordered output.
- Pan Fill-mode crops per image for precise framing.
- Print all images in sequence with orientation handling and optional cut markers.

## Installation Guide

### Method A (Recommended): Conda Environment

Use this if you want clean dependency isolation similar to the local project setup.

```bash
conda create -n easy-photo-printer python=3.13 -y
conda activate easy-photo-printer
pip install PySide6==6.11.0 Pillow==12.2.0
python main.py
```

### Method B (Quick): Python venv

```bash
python -m venv .venv
.venv\Scripts\activate
pip install PySide6==6.11.0 Pillow==12.2.0
python main.py
```

## Usage - Execution

Start the app:

```bash
python main.py
```

## Usage - Workflows

### Window Layout

- The top toolbar keeps Open Photos, Clear All, and Print All within easy reach.
- The left settings sidebar separates All photos defaults from Selected photo overrides.
- Under All photos, expand or collapse Paper, Layout, and Appearance using their
  arrow buttons. Layout starts collapsed; expand it for print size, margins, and cut markers.
- Drag the divider between the sidebar and preview to resize them. Scroll the
  sidebar when settings do not fit; the preview and thumbnail strip stay in place.
- The View menu still controls paper and crop shadows.

### 1) Batch Load and Preview

Scenario: You have a folder of event photos and want to print a curated subset quickly.

Workflow:

1. Click Open Photos....
2. Select one or more image files (JPG/PNG/BMP/TIFF/WebP).
3. Use the thumbnail strip to switch between photos.
4. Confirm each image in the main canvas preview.
5. Check metadata and print PPI overlay in the lower-left area.

Example Use Case:

You imported 40 photos from a camera and need to choose the best 12 for physical prints without opening each file in a separate editor.

### 2) Crop Control with Fit Modes

Scenario: A portrait photo gets awkwardly cropped when printed on 4x6 paper.

Workflow:

1. Set global Fit to Fill (crop), Fit (letterbox), or Stretch.
2. Select a photo in the thumbnail bar.
3. Use Fit under Selected photo in the sidebar to override only that image if needed.
4. In Fill mode, drag inside the print area to adjust crop framing.
5. Click Reset crop to recenter if the framing goes off-track.

Example Use Case:

You want most photos to use Fill, but one wide group shot should use Fit so nobody gets cropped out.

### 3) Custom Print Area and Cut Markers

Scenario: You are printing wallet-sized crops on larger paper for manual trimming.

Workflow:

1. Set Size to Custom size.
2. Enter target W and H dimensions in inches.
3. Enable Cut markers.
4. Verify the dashed print-area border in preview.
5. Toggle Paper shadow / Show crop shadow from View to inspect boundaries.

Example Use Case:

You print 3.5x5 images on letter paper and use the markers as trim guides for consistent cuts.

### 4) Add Margins Inside the Print Size

Scenario: You want a clean white border but still want the selected print size to stay exact.

Workflow:

1. Choose Full paper or enter a custom W and H print area.
2. Expand Layout, open Margins..., enable Add margins, then select Inches or Percent.
3. Enter one shared margin, or enable Set edges separately.
4. Enter separate top, right, bottom, and left values as needed.
5. Verify the orange dotted image-area border in preview; the dashed blue border
   marks the print size, and blue tint shows the crop-shadow context.
6. Print normally; the photo is inset inside the selected print size.

Example Use Case:

You print a 4x6 photo with a 0.25-inch border, or a 5% border that scales with the print size. The printed footprint remains 4x6, while the image itself is rendered inside the remaining area. Use independent edges to leave extra room at the bottom for a label or mat-style border.

### 5) Print Batch with Orientation Handling

Scenario: Your batch includes both portrait and landscape images and you want fewer manual print reruns.

Workflow:

1. Choose a paper preset.
2. Set Orientation to Portrait, Landscape, or Auto.
3. Click Print All.
4. Confirm printer and settings in the system print dialog.
5. Monitor status messages while pages are sent.

Example Use Case:

A mixed phone-photo batch prints in one pass, with Auto orientation reducing wrong-rotation pages.

### 6) Color Mode and Dithering

1. Under All photos > Appearance, choose a Color mode: Full color (24-bit), 256 colors (8-bit indexed),
   16 colors (4-bit indexed), Grayscale (8-bit), or Black & white (1-bit).
2. Enable Dithering to approximate missing tones with dots in indexed-color or
   black-and-white output. Disable it for flatter colors or a hard black/white
   threshold. It is not applicable to full color or grayscale.
3. Select a thumbnail and use Color mode under Selected photo to override the global
   mode. The Dithering dropdown can inherit, enable, or disable dithering
   independently for that photo.
4. Preview the result, then print normally. Global preferences are remembered;
   per-photo overrides last until the batch is replaced or cleared.

Original files and thumbnails remain unchanged. The blue-tinted crop-shadow
context shows the original image, while the print area shows the selected effect.
Color reduction happens after resizing/cropping through shared preview/print
processing. Dither dots and adaptive palettes can differ at screen and print
resolutions; the preview is not a printer color proof.

These settings change image appearance, not the printer's internal bit depth or
guaranteed ink usage. Output is still sent to Qt as RGB. Increasing an image's
bit depth cannot recover missing detail.

## Development

### Project Structure

```text
EasyPhotoPrinterApp/
├─ main.py
├─ config/
│  └─ paper_sizes.json
├─ core/
│  ├─ __init__.py
│  ├─ image_processor.py
│  └─ photo_info.py
└─ ui/
   ├─ __init__.py
   ├─ main_window.py
   ├─ photo_canvas.py
   └─ thumbnail_bar.py
```

### Key Directories

- config/: Editable JSON presets for paper sizes.
- core/: Image rendering logic and metadata/PPI calculations.
- ui/: Main window, preview canvas, thumbnail strip, and print actions.

### Tests and Style

Run the color-processing and offscreen UI/PDF integration tests:

```bash
python -m unittest discover -s tests -v
```

The tests use temporary preferences and files; no physical printer is needed.
No project-specific linter config is committed yet.

Current practical checks:

```bash
python -m compileall .
python main.py
```

Suggested next step for style checks (optional):

```bash
pip install ruff
ruff check .
```

### Windows Installer Build

The Windows installer is built on top of the PyInstaller EXE, then wrapped with Inno Setup.

Required tools:

- Python environment with PySide6 and Pillow installed
- PyInstaller
- Inno Setup 6 (`ISCC.exe`)

Build commands:

```powershell
.\build_exe.ps1
.\build_installer.ps1
```

To set a release version explicitly:

```powershell
.\build_installer.ps1 -Version 1.2.3
```

Installer output:

- `dist\installer\EasyPhotoPrinter-Setup-<version>.exe`

What the installer includes:

- The packaged app executable
- `README.md`
- `INSTALL_AND_USAGE.md`
- `screenshot.jpg`

Install behavior:

- Per-user install under `%LOCALAPPDATA%\Programs\EasyPhotoPrinter`
- Start Menu shortcut
- Desktop shortcut
- Uninstaller entry
- Upgrade-friendly AppId so newer builds replace older ones cleanly

## Requirements

Core runtime dependencies currently used by the app:

- Python 3.13.2
- PySide6 6.11.0
- Pillow 12.2.0
