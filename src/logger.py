import logging
import json
from datetime import datetime
import sys

def setup_logging(level: str = "INFO"):
    """Configure structured logging."""
    
    logger = logging.getLogger("sangam_talks")
    logger.setLevel(level)
    
    # Console handler
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger

def log_event(logger, event_type: str, data: dict):
    """Log structured event."""
    logger.info(json.dumps({
        "timestamp": datetime.utcnow().isoformat(),
        "event": event_type,
        "data": data
    }))

logger = setup_logging()
