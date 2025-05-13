import json
import logging
import os
from typing import Dict, Any

from commons.constants import CONFIG_LAST_PROCESSED_ROW, DEFAULT_LAST_PROCESSED_ROW, CONFIG_USER_IDS, DEBANIKS_USER_ID

logger = logging.getLogger(__name__)

class ConfigManager:
    """Class for managing bot configuration"""

    def __init__(self, config_file: str):
        """Initialize config manager with config file path"""
        self.config_file = config_file
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            else:
                default_config = {
                    CONFIG_LAST_PROCESSED_ROW: DEFAULT_LAST_PROCESSED_ROW,
                    CONFIG_USER_IDS: [DEBANIKS_USER_ID]  # List of authorized Telegram user IDs
                }
                self._save_config(default_config)
                return default_config
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {CONFIG_LAST_PROCESSED_ROW: DEFAULT_LAST_PROCESSED_ROW, CONFIG_USER_IDS: [DEBANIKS_USER_ID]}

    def _save_config(self, config: Dict[str, Any]) -> bool:
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False

    def get_last_processed_row(self) -> int:
        """Get the index of the last processed row"""
        return self.config.get(CONFIG_LAST_PROCESSED_ROW, DEFAULT_LAST_PROCESSED_ROW)

    def update_last_processed_row(self, row_index: int) -> bool:
        """Update the last processed row index"""
        self.config[CONFIG_LAST_PROCESSED_ROW] = row_index
        return self._save_config(self.config)
