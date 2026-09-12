# File: core/logger.py
"""
Advanced colored console logger for Xrypton.


Usage
-----
    from core.logger import log

    log.info("info test")
    log.success("Loaded cog", "cogs.moderation")
    log.warning("Shard lagged", shard=3)
"""
from __future__ import annotations

import os
import sys
import time
import threading
from collections import deque
from datetime import datetime
from typing import Any, Deque, Optional, TextIO


# --------------------------------------------------------------------------- #
#  ANSI colour palette
# --------------------------------------------------------------------------- #
class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GREY = "\033[90m"

    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"


def _enable_windows_ansi() -> bool:
    """Enable VT processing on Windows terminals. Returns True if TTY-capable."""
    if os.name != "nt":
        return sys.stdout.isatty()
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # Enable EN_VIRTUAL_TERMINAL_PROCESSING (0x0004) on stdout (handle -11)
        for handle in (-11, -12):
            mode = ctypes.c_uint32()
            h = kernel32.GetStdHandle(handle)
            if h in (0, -1):
                continue
            if kernel32.GetConsoleMode(h, ctypes.byref(mode)):
                kernel32.SetConsoleMode(h, mode.value | 0x0004)
        return sys.stdout.isatty()
    except Exception:
        return False

def _reconfigure_streams() -> None:
    # Force UTF-8 output so icons and box-drawing render on legacy Windows
    # code pages (cp1252), where emoji otherwise raise UnicodeEncodeError and
    # every log line is silently swallowed.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            if (stream.encoding or "").lower().replace("-", "") != "utf8":
                reconfigure(encoding="utf-8", errors="replace")
            else:
                reconfigure(errors="replace")
        except (ValueError, OSError):
            pass
_reconfigure_streams()


# --------------------------------------------------------------------------- #
#  Levels
# --------------------------------------------------------------------------- #
class Level:
    TRACE = 5
    DEBUG = 10
    INFO = 20
    SUCCESS = 25
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

    NAMES = {
        TRACE: "TRACE",
        DEBUG: "DEBUG",
        INFO: "INFO",
        SUCCESS: "OK",
        WARNING: "WARN",
        ERROR: "ERROR",
        CRITICAL: "CRIT",
    }


#        level      label colour         message colour      icon
_STYLES: dict[int, tuple[str, str, str, str]] = {
    Level.TRACE: (Color.DIM + Color.GREY, Color.GREY, Color.DIM, ""),
    Level.DEBUG: (Color.CYAN, Color.GREY, Color.DIM, ""),
    Level.INFO: (Color.BRIGHT_BLUE, Color.WHITE, Color.RESET, ""),
    Level.SUCCESS: (Color.BRIGHT_GREEN, Color.GREEN, Color.RESET, ""),
    Level.WARNING: (Color.BRIGHT_YELLOW, Color.YELLOW, Color.RESET, ""),
    Level.ERROR: (Color.BRIGHT_RED, Color.RED, Color.BRIGHT_RED, ""),
    Level.CRITICAL: (
        Color.BOLD + Color.BRIGHT_WHITE + Color.RED,
        Color.BRIGHT_RED,
        Color.BOLD + Color.BRIGHT_RED,
        "",
    ),
}

_LABEL_WIDTH = 5

class Logger:

    _MAX_BUFFER = 2000

    def __init__(
        self,
        name: str = "Xrypton",
        *,
        level: int = Level.TRACE,
        stream: Optional[TextIO] = None,
        use_color: Optional[bool] = None,
        show_icons: bool = True,
        show_name: bool = True,
        force_color: bool = False,
        file_path: Optional[str] = None,
        file_level: int = Level.DEBUG,
    ) -> None:
        self.name = name
        self.level = level
        self.stream = stream if stream is not None else sys.stdout
        self.show_icons = show_icons
        self.show_name = show_name
        self.force_color = force_color
        self.file_path = file_path
        self.file_level = file_level

        if use_color is None:
            use_color = _enable_windows_ansi()
        # Honour the NO_COLOR convention (https://no-color.org/)
        if os.getenv("NO_COLOR"):
            use_color = False
        self.use_color = use_color

        self._lock = threading.RLock()
        self._file: Optional[TextIO] = None
        self._buffer: Deque[str] = deque(maxlen=self._MAX_BUFFER)
        if file_path:
            self._open_file()

    # -- plumbing ---------------------------------------------------------- #
    def _open_file(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)
            self._file = open(self.file_path, "a", encoding="utf-8")
        except OSError:
            self._file = None

    def _paint(self, text: str, *codes: str) -> str:
        if not self.use_color or not codes:
            return text
        return "".join(codes) + text + Color.RESET

    def get(self, name: str) -> "Logger":
        """Return a child logger sharing this logger's configuration."""
        return Logger(
            name,
            level=self.level,
            stream=self.stream,
            use_color=self.use_color,
            show_icons=self.show_icons,
            show_name=self.show_name,
            force_color=self.force_color,
            file_path=self.file_path,
            file_level=self.file_level,
        )

    # -- core emit --------------------------------------------------------- #
    def log(
        self,
        level: int,
        message: Any,
        *args: Any,
        name: Optional[str] = None,
        exc_info: bool = False,
        stacklevel: int = 2,
        **kwargs: Any,
    ) -> None:
        if level < self.level:
            return
        label_color, _accent, msg_color, icon = _STYLES.get(level, _STYLES[Level.INFO])

        timestamp = datetime.now().strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"
        ts_text = self._paint(timestamp, Color.GREY)
        label_text = self._paint(Level.NAMES.get(level, "INFO").ljust(_LABEL_WIDTH), Color.BOLD, label_color)

        icon_text = f"{icon} " if (self.show_icons and icon) else ""
        prefix = f"{ts_text} {label_text} {icon_text}"
        if self.show_name:
            prefix += self._paint(f"[{name or self.name}] ", Color.MAGENTA)

        text = self._format_message(message, args, kwargs)

        # Source location only for the most verbose levels.
        if level <= Level.DEBUG:
            loc = self._caller_location(stacklevel)
            if loc:
                prefix += self._paint(f"({loc}) ", Color.GREY)

        coloured_line = prefix + self._paint(text, msg_color)
        plain_line = self._strip(prefix) + text
        self._emit(coloured_line, plain_line, level, exc_info)

    # -- helpers ----------------------------------------------------------- #
    @staticmethod
    def _strip(text: str) -> str:
        """Remove ANSI escape sequences for the plain-text (file) copy."""
        out = []
        i = 0
        while i < len(text):
            if text[i] == "\033" and i + 1 < len(text) and text[i + 1] == "[":
                j = i + 2
                while j < len(text) and not text[j].isalpha():
                    j += 1
                i = j + 1
                continue
            out.append(text[i])
            i += 1
        return "".join(out)

    @staticmethod
    def _format_message(message: Any, args: tuple, kwargs: dict) -> str:
        text = str(message)
        if args:
            try:
                text = text.format(*args)
            except (IndexError, KeyError, ValueError):
                text = text + " + " ".join(str(a) for a in args)"
        if kwargs:
            extra = "  ".join(f"{k}={v}" for k, v in kwargs.items())
            text = f"{text}  {extra}"
        return text

    def _caller_location(self, stacklevel: int) -> Optional[str]:
        """Return ``file:line`` of the caller that triggered the log."""
        import traceback as _tb

        stack = _tb.extract_stack()
        # Skip this frame, _caller_location, log(), and the level helper.
        idx = len(stack) - 1 - stacklevel
        while idx >= 0 and stack[idx].filename == __file__:
            idx -= 1
        if idx < 0:
            return None
        frame = stack[idx]
        return f"{os.path.basename(frame.filename)}:{frame.lineno}"

    def _emit(
        self,
        coloured: str,
        plain: str,
        level: int,
        exc_info: bool = False,
    ) -> None:
        with self._lock:
            try:
                self.stream.write(coloured + "\n")
                self.stream.flush()
            except Exception:
                pass
            self._buffer.append(plain)
            if self._file and level >= self.file_level:
                try:
                    self._file.write(plain + "\n")
                    self._file.flush()
                except Exception:
                    pass
            if exc_info:
                import traceback as _tb

                tb = _tb.format_exc()
                if tb and tb.strip() != "NoneType: None":
                    try:
                        self.stream.write(_tb.format_exc())
                        self.stream.flush()
                    except Exception:
                        pass

    # -- public API -------------------------------------------------------- #
    def trace(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self.log(Level.TRACE, message, *args, stacklevel=3, **kwargs)

    def debug(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self.log(Level.DEBUG, message, *args, stacklevel=3, **kwargs)

    def info(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self.log(Level.INFO, message, *args, stacklevel=3, **kwargs)

    def success(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self.log(Level.SUCCESS, message, *args, stacklevel=3, **kwargs)

    def warning(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self.log(Level.WARNING, message, *args, stacklevel=3, **kwargs)

    # alias
    warn = warning

    def error(self, message: Any, *args: Any, exc_info: bool = False, **kwargs: Any) -> None:
        self.log(Level.ERROR, message, *args, exc_info=exc_info, stacklevel=3, **kwargs)

    def critical(self, message: Any, *args: Any, exc_info: bool = False, **kwargs: Any) -> None:
        self.log(Level.CRITICAL, message, *args, exc_info=exc_info, stacklevel=3, **kwargs)

    def exception(self, message: Any, *args: Any, **kwargs: Any) -> None:
        """Log an ERROR together with the current exception traceback."""
        self.log(Level.ERROR, message, *args, exc_info=True, stacklevel=3, **kwargs)

    def traceback(
        self,
        error: BaseException,
        message: str = "Unhandled exception",
        *,
        level: int = Level.ERROR,
    ) -> None:
        # Log a given exception object together with its formatted traceback.
        # Unlike exception() (which reads sys.exc_info()), this accepts any
        # exception instance, e.g. the `error` in a discord.py error handler.
        self.log(level, message, stacklevel=3)
        import traceback as _tb
        formatted = "".join(
            _tb.format_exception(type(error), error, error.__traceback__)
        ).rstrip()
        for line in formatted.splitlines():
            self.log(level, self._paint(line, Color.RED), stacklevel=3)

    # -- decorative helpers ------------------------------------------------ #
    def banner(self, title: str, subtitle: str = "") -> None:
        """Print a boxed startup banner."""
        width = max(len(title), len(subtitle)) + 4
        top = "╭" + "─" * width + "╮"
        bottom = "╰" + "─" * width + "╯"
        lines = [top]
        lines.append("│ " + title.ljust(width - 2) + " │")
        if subtitle:
            lines.append("│ " + subtitle.ljust(width - 2) + " │")
        lines.append(bottom)
        for line in lines:
            self.log(Level.INFO, self._paint(line, Color.BRIGHT_CYAN), stacklevel=3)

    def divider(self, label: str = "") -> None:
        if label:
            text = f"── {label} ".ljust(60, "─")
        else:
            text = "─" * 60
        self.log(Level.INFO, self._paint(text, Color.GREY), stacklevel=3)

    def module(self, action: str, name: str) -> None:
        """Log a cog/module lifecycle event, coloured by success or failure."""
        lowered = action.lower()
        if lowered in {"loaded", "sync", "synced", "enabled", "ready"}:
            self.success(f"{action} {name}", name=self.name)
        elif lowered in {"failed", "error", "unloaded", "disabled"}:
            self.error(f"{action} {name}", name=self.name)
        else:
            self.info(f"{action} {name}", name=self.name)

    def kv(self, title: str, **fields: Any) -> None:
        """Log a titled block of key/value pairs, aligned in columns."""
        self.info(title)
        if not fields:
            return
        key_width = max(len(str(k)) for k in fields)
        for key, value in fields.items():
            row = f"  {str(key).rjust(key_width)} : {value}"
            self.log(Level.INFO, self._paint(row, Color.GREY), stacklevel=3)

    # -- diagnostics ------------------------------------------------------- #
    def dump(self, tail: Optional[int] = None) -> None:
        """Re-print the buffered lines (optionally just the last ``tail``)."""
        with self._lock:
            lines = list(self._buffer)
        if tail is not None:
            lines = lines[-tail:]
        for line in lines:
            try:
                self.stream.write(self._paint(line, Color.GREY) + "\n")
            except Exception:
                pass
        try:
            self.stream.flush()
        except Exception:
            pass

    def close(self) -> None:
        with self._lock:
            if self._file:
                try:
                    self._file.close()
                except Exception:
                    pass
                self._file = None


# --------------------------------------------------------------------------- #
#  Singleton access
# --------------------------------------------------------------------------- #
_LOG_FILE = os.getenv("LOG_FILE") or "logs/xrypton.log"
_LOG_LEVEL = os.getenv("LOG_LEVEL", "TRACE").upper()

_default_level = getattr(Level, _LOG_LEVEL, Level.TRACE)
if not isinstance(_default_level, int):
    _default_level = Level.TRACE

log = Logger(
    "Xrypton",
    level=_default_level,
    file_path=_LOG_FILE if _LOG_FILE else None,
    file_level=Level.DEBUG,
)


def get_logger(name: str) -> Logger:
    """Return a named child of the global logger."""
    return log.get(name)


__all__ = ["Logger", "Level", "Color", "log", "get_logger"]
