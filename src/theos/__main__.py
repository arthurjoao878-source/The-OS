from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from theos.bootstrap import build_action_registry, build_ai_provider, build_memory_service
from theos.shell.assistant.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow(
        build_action_registry(),
        build_memory_service(),
        build_ai_provider(),
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
