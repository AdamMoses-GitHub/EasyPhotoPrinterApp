# INSTALL_AND_USAGE

## Feature Recap

This tool lets you:

- Load a batch of photos and switch between them via thumbnails.
- Preview paper size, print area, and fit mode before printing.
- Choose global fit behavior and override it per photo.
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
3. Use This photo to override fit mode for only that image if needed.
4. In Fill mode, drag inside the print area to adjust crop framing.
5. Click Reset crop to recenter if the framing goes off-track.

Example Use Case:

You want most photos to use Fill, but one wide group shot should use Fit so nobody gets cropped out.

### 3) Custom Print Area and Cut Markers

Scenario: You are printing wallet-sized crops on larger paper for manual trimming.

Workflow:

1. Uncheck Full paper.
2. Enter target W and H dimensions in inches.
3. Enable Cut markers.
4. Verify the dashed print-area border in preview.
5. Toggle Paper shadow / Show crop shadow from View to inspect boundaries.

Example Use Case:

You print 3.5x5 images on letter paper and use the markers as trim guides for consistent cuts.

### 4) Print Batch with Orientation Handling

Scenario: Your batch includes both portrait and landscape images and you want fewer manual print reruns.

Workflow:

1. Choose a paper preset.
2. Set Orientation to Portrait, Landscape, or Auto.
3. Click Print All.
4. Confirm printer and settings in the system print dialog.
5. Monitor status messages while pages are sent.

Example Use Case:

A mixed phone-photo batch prints in one pass, with Auto orientation reducing wrong-rotation pages.

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

No project-specific automated test suite or linter config is committed yet.

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

## Requirements

Core runtime dependencies currently used by the app:

- Python 3.13.2
- PySide6 6.11.0
- Pillow 12.2.0
