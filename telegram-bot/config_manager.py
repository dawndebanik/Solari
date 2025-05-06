import json
import logging
import os
from typing import Dict, Any

from constants import CONFIG_LAST_PROCESSED_ROW, DEFAULT_LAST_PROCESSED_ROW, CONFIG_USER_IDS

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
                    CONFIG_USER_IDS: []  # List of authorized Telegram user IDs
                }
                self._save_config(default_config)
                return default_config
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {CONFIG_LAST_PROCESSED_ROW: DEFAULT_LAST_PROCESSED_ROW, CONFIG_USER_IDS: []}

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

    def is_authorized_user(self, user_id: int) -> bool:
        """Check if a user is authorized"""
        if not self.config.get(CONFIG_USER_IDS):
            # If no users configured, allow all (you may want to change this)
            return True
        return user_id in self.config.get(CONFIG_USER_IDS, [])

    def add_authorized_user(self, user_id: int) -> bool:
        """Add a user to the authorized users list"""
        if user_id not in self.config.get(CONFIG_USER_IDS, []):
            if CONFIG_USER_IDS not in self.config:
                self.config[CONFIG_USER_IDS] = []
            self.config[CONFIG_USER_IDS].append(user_id)
            return self._save_config(self.config)
        return True
