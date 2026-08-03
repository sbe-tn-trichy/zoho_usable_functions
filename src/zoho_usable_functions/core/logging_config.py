import logging
import sys

def setup_logging(level=logging.INFO, verbose: bool = False):
    """
    Configures a basic console logging handler for the application scripts.
    """
    target_level = logging.DEBUG if verbose else level
    logging.basicConfig(
        level=target_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
