from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import QThreadPool

from mi_nube.app.bootstrap import create_application


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cliente de escritorio Mi Nube")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Crea la ventana, procesa eventos y termina sin interacción.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    application, window = create_application(sys.argv if argv is None else [sys.argv[0], *argv])
    window.show()

    if args.smoke_test:
        application.processEvents()
        QThreadPool.globalInstance().waitForDone(15000)
        application.processEvents()
        window.close()
        return 0

    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
