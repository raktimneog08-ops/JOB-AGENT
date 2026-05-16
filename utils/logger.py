"""
Structured logging utility for the job aggregation agent.
Provides colored console output and file logging with timestamps.
"""

import logging
import sys
from datetime import datetime


class JobAgentLogger:
    """Custom logger with consistent formatting for the job agent."""

    _instance = None

    def __new__(cls, log_level: str = "INFO", log_file: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, log_level: str = "INFO", log_file: str = None):
        self.logger = logging.getLogger("JobAgent")
        level = getattr(logging, log_level.upper(), logging.INFO)
        self.logger.setLevel(level)
        
        # Re-initialize handlers only on first call OR if level/file params have changed
        if self._initialized:
            # Check if level has changed
            current_level = self.logger.level
            if current_level != level:
                self.logger.setLevel(level)
                for handler in self.logger.handlers:
                    handler.setLevel(level)
            return
        
        self._initialized = True
        self.logger.handlers.clear()

        # Console handler with colored output
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(self._ColoredFormatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        self.logger.addHandler(console_handler)

        # File handler (optional)
        if log_file:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
            self.logger.addHandler(file_handler)

    class _ColoredFormatter(logging.Formatter):
        """Custom formatter with terminal color codes."""

        COLORS = {
            "DEBUG": "\033[36m",      # Cyan
            "INFO": "\033[32m",       # Green
            "WARNING": "\033[33m",    # Yellow
            "ERROR": "\033[31m",      # Red
            "CRITICAL": "\033[41m",   # Red background
            "RESET": "\033[0m",
        }

        def format(self, record):
            log_message = super().format(record)
            color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
            return f"{color}{log_message}{self.COLORS['RESET']}"

    def debug(self, message: str, module: str = ""):
        prefix = f"[{module}] " if module else ""
        self.logger.debug(f"{prefix}{message}")

    def info(self, message: str, module: str = ""):
        prefix = f"[{module}] " if module else ""
        self.logger.info(f"{prefix}{message}")

    def warning(self, message: str, module: str = ""):
        prefix = f"[{module}] " if module else ""
        self.logger.warning(f"{prefix}{message}")

    def error(self, message: str, module: str = "", exc_info: bool = False):
        prefix = f"[{module}] " if module else ""
        self.logger.error(f"{prefix}{message}", exc_info=exc_info)

    def critical(self, message: str, module: str = "", exc_info: bool = False):
        prefix = f"[{module}] " if module else ""
        self.logger.critical(f"{prefix}{message}", exc_info=exc_info)


# Global singleton instance
def get_logger(log_level: str = "INFO", log_file: str = None) -> JobAgentLogger:
    """Get or create the global logger instance."""
    return JobAgentLogger(log_level, log_file)