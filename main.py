import sys
from pathlib import Path


def _configure_frozen_dll_paths() -> None:
    """Help Windows find Qt/PySide DLLs in PyInstaller frozen builds."""
    if not getattr(sys, "frozen", False):
        return

    import os
    from pathlib import Path

    meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    candidates = [
        meipass,
        meipass / "Library" / "bin",
        meipass / "PySide6",
    ]
    for path in candidates:
        if path.exists():
            os.add_dll_directory(str(path))


def _resource_path(relative: str) -> Path:
    """Resolve resource paths in source and PyInstaller one-file builds."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / relative
    return Path(__file__).resolve().parent / relative


def main():
    _configure_frozen_dll_paths()

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
    app_icon_path = _resource_path("assets/app.ico")
    if app_icon_path.exists():
        app.setWindowIcon(QIcon(str(app_icon_path)))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
