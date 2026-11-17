import os
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
CONFIG_FILE = PROJECT_ROOT / "config.yml"


class Config:
    """Configuration manager for the application."""

    def __init__(self, config_file=None):
        """Initialize configuration from YAML file."""
        self.config_file = config_file or CONFIG_FILE
        self.config = self._load_config()

    def _load_config(self):
        """Load configuration from YAML file."""
        if not self.config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_file}")

        with open(self.config_file, "r") as f:
            config = yaml.safe_load(f)

        return config

    def get_download_path(self):
        """Get the default download path."""
        path = self.config.get("download_path")
        if path:
            # Expand user home directory if present
            path = os.path.expanduser(path)
            # Create directory if it doesn't exist
            os.makedirs(path, exist_ok=True)
        return path


# Global config instance
config = Config()
