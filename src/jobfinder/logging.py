from __future__ import annotations

import logging


def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    if not verbose:
        # Keep command output readable by default.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("faiss.loader").setLevel(logging.WARNING)
