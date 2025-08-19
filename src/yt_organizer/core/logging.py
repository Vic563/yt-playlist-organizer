"""Logging configuration for YouTube Playlist Organizer."""

import logging
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table


# Global console instance for rich output
console = Console()


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    rich_output: bool = True
) -> logging.Logger:
    """
    Set up logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        rich_output: Whether to use rich formatting for console output
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("yt_organizer")
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Console handler with rich formatting
    if rich_output:
        console_handler = RichHandler(
            console=console,
            rich_tracebacks=True,
            show_time=True,
            show_path=False,
        )
        console_handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
    
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Optional logger name (will be prefixed with 'yt_organizer.')
    
    Returns:
        Logger instance
    """
    if name:
        return logging.getLogger(f"yt_organizer.{name}")
    return logging.getLogger("yt_organizer")


def create_progress_bar() -> Progress:
    """Create a rich progress bar for long-running operations."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


def print_stats_table(stats: dict) -> None:
    """
    Print statistics in a formatted table.
    
    Args:
        stats: Dictionary of statistics to display
    """
    table = Table(title="Processing Statistics", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    for key, value in stats.items():
        # Format the key to be more readable
        formatted_key = key.replace("_", " ").title()
        table.add_row(formatted_key, str(value))
    
    console.print(table)


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]⚠[/yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[blue]ℹ[/blue] {message}")


class LogContext:
    """Context manager for temporary log level changes."""
    
    def __init__(self, level: str):
        self.level = level
        self.logger = get_logger()
        self.original_level = self.logger.level
    
    def __enter__(self):
        self.logger.setLevel(getattr(logging, self.level.upper()))
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.setLevel(self.original_level)
