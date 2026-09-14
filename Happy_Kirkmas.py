"""
Desktop cursor-accuracy trainer.

The program displays a figure made from dots on a transparent desktop
overlay. Figures are loaded from ``stick_figure.txt`` located beside the
script or packaged executable.

File format
-----------
Line 1:
    Success message displayed after clicking a target.

Line 2:
    Hex colour used for special ``T`` dots.

Line 3 onward:
    Figure definition.

Figure characters
-----------------
O
    Normal white dot.

X
    Target dot. It looks like a normal dot unless target debugging is
    enabled.

T
    Special dot rendered using the hex colour from line 2.

Space
    Empty space.

Controls
--------
R
    Interrupt the current figure lifecycle and immediately respawn.

Esc
    Exit the application.

The system tray menu can also enable or disable the trainer, reload the
figure file, respawn the figure, or exit the application.
"""

from __future__ import annotations

import math
import queue
import random
import sys
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox

import pystray
from PIL import Image, ImageDraw


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POINT_SPACING = 12

DOT_RADIUS = 4
TARGET_HIT_RADIUS = 8
TARGET_HIT_RADIUS_SQUARED = TARGET_HIT_RADIUS**2

SCREEN_MARGIN = 100

CELEBRATION_PARTICLE_COUNT = 24
CELEBRATION_DURATION_MS = 1_200
RESPAWN_DELAY_MS = 1_500

# Approximately 30 FPS.
ANIMATION_FRAME_MS = 33

# Tray actions do not need frame-rate-level polling.
TRAY_QUEUE_CHECK_MS = 100

TRANSPARENT_COLOR = "#010101"
DOT_COLOR = "white"

DEBUG_SHOW_TARGETS = False
DEBUG_TARGET_COLOR = "red"


# ---------------------------------------------------------------------------
# Built-in fallback figure
# ---------------------------------------------------------------------------

DEFAULT_FIGURE = """
Congrats!
#ffaa5f
OOOOO   TTTTTTT   XXXXX   OOOOO  O    O
O          T        X    O       O   O
O          T        X    O       O O
OOOOO      T        X    O       OO
    O      T        X    O       O O
    O      T        X    O       O   O
OOOOO      T      XXXXX   OOOOO  O     O
"""


# ---------------------------------------------------------------------------
# Application paths
# ---------------------------------------------------------------------------


def get_application_directory() -> Path:
    """Return the directory containing the script or packaged executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


APPLICATION_DIRECTORY = get_application_directory()
FIGURE_FILE = APPLICATION_DIRECTORY / "stick_figure.txt"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FigurePoint:
    """Represent one immutable point in a figure."""

    x: float
    y: float
    point_type: str

    @property
    def is_target(self) -> bool:
        """Return whether this point is a clickable target."""
        return self.point_type == "target"


@dataclass(frozen=True, slots=True)
class FigureDefinition:
    """Store a fully processed, immutable figure definition."""

    message: str
    special_color: str
    points: tuple[FigurePoint, ...]
    targets: tuple[tuple[float, float], ...]
    width: float
    height: float


@dataclass(slots=True)
class Particle:
    """Represent one mutable celebration particle."""

    item: int
    dx: float
    dy: float


# ---------------------------------------------------------------------------
# Figure loading
# ---------------------------------------------------------------------------


def is_valid_hex_color(value: str) -> bool:
    """Return whether ``value`` is a valid ``#RRGGBB`` colour."""
    if len(value) != 7 or not value.startswith("#"):
        return False

    return all(
        character in "0123456789abcdefABCDEF"
        for character in value[1:]
    )


def get_figure_source(file_path: Path) -> list[str]:
    """Return figure-definition lines from disk or the built-in fallback."""
    if file_path.exists():
        return file_path.read_text(
            encoding="utf-8"
        ).splitlines()

    return DEFAULT_FIGURE.strip("\n").splitlines()


def center_figure(
    points: list[FigurePoint],
) -> tuple[FigurePoint, ...]:
    """Return ``points`` centered around coordinate ``(0, 0)``."""
    min_x = min(point.x for point in points)
    max_x = max(point.x for point in points)

    min_y = min(point.y for point in points)
    max_y = max(point.y for point in points)

    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2

    return tuple(
        FigurePoint(
            x=point.x - center_x,
            y=point.y - center_y,
            point_type=point.point_type,
        )
        for point in points
    )


def get_figure_size(
    points: tuple[FigurePoint, ...],
) -> tuple[float, float]:
    """Return the width and height occupied by ``points``."""
    min_x = min(point.x for point in points)
    max_x = max(point.x for point in points)

    min_y = min(point.y for point in points)
    max_y = max(point.y for point in points)

    return (
        max_x - min_x,
        max_y - min_y,
    )


def get_target_coordinates(
    points: tuple[FigurePoint, ...],
) -> tuple[tuple[float, float], ...]:
    """Return relative coordinates for every target in ``points``."""
    return tuple(
        (point.x, point.y)
        for point in points
        if point.is_target
    )


def load_text_figure(
    file_path: Path,
    spacing: int = POINT_SPACING,
) -> FigureDefinition:
    """Load, validate, center, and preprocess a complete figure.

    Args:
        file_path:
            Path to ``stick_figure.txt``.

        spacing:
            Pixel distance represented by one character position.

    Returns:
        A fully processed immutable figure definition.

    Raises:
        OSError:
            If an existing figure file cannot be read.

        ValueError:
            If the figure definition is malformed.
    """
    lines = get_figure_source(file_path)

    if len(lines) < 3:
        raise ValueError(
            "stick_figure.txt must contain at least three lines:\n\n"
            "1. Success message\n"
            "2. Special-dot hex colour\n"
            "3+. Figure definition"
        )

    message = lines[0].strip()
    special_color = lines[1].strip()
    figure_lines = lines[2:]

    if not message:
        raise ValueError(
            "The first line must contain a success message."
        )

    if not is_valid_hex_color(special_color):
        raise ValueError(
            "The second line must contain a valid #RRGGBB hex colour, "
            "such as #ffffff or #f2c317."
        )

    point_types = {
        "O": "normal",
        "X": "target",
        "T": "special",
    }

    points: list[FigurePoint] = []

    for row, line in enumerate(figure_lines):
        for column, character in enumerate(line):
            point_type = point_types.get(character)

            if point_type is None:
                continue

            points.append(
                FigurePoint(
                    x=column * spacing,
                    y=row * spacing,
                    point_type=point_type,
                )
            )

    if not points:
        raise ValueError(
            "The figure must contain at least one O, X, or T."
        )

    if not any(point.is_target for point in points):
        raise ValueError(
            "The figure must contain at least one X target."
        )

    centered_points = center_figure(points)

    width, height = get_figure_size(
        centered_points
    )

    targets = get_target_coordinates(
        centered_points
    )

    return FigureDefinition(
        message=message,
        special_color=special_color,
        points=centered_points,
        targets=targets,
        width=width,
        height=height,
    )


# ---------------------------------------------------------------------------
# Tray icon
# ---------------------------------------------------------------------------


def create_tray_image() -> Image.Image:
    """Create a simple stick-figure image for the system tray."""
    size = 64

    image = Image.new(
        "RGBA",
        (size, size),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(image)

    draw.ellipse(
        (24, 5, 40, 21),
        fill="white",
    )

    draw.line(
        (32, 21, 32, 43),
        fill="white",
        width=4,
    )

    draw.line(
        (15, 30, 49, 30),
        fill="white",
        width=4,
    )

    draw.line(
        (32, 43, 18, 59),
        fill="white",
        width=4,
    )

    draw.line(
        (32, 43, 46, 59),
        fill="white",
        width=4,
    )

    return image


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------


class CursorTrainer:
    """Run the desktop cursor-accuracy trainer."""

    def __init__(
        self,
        figure: FigureDefinition,
    ) -> None:
        """Initialize the desktop overlay and system tray."""
        self.figure = figure

        self.enabled = True
        self.closing = False

        self.root = tk.Tk()

        self.root.overrideredirect(True)
        self.root.attributes(
            "-topmost",
            True,
        )

        self.root.configure(
            bg=TRANSPARENT_COLOR
        )

        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()

        self.root.geometry(
            f"{self.screen_width}x{self.screen_height}+0+0"
        )

        self.root.wm_attributes(
            "-transparentcolor",
            TRANSPARENT_COLOR,
        )

        self.canvas = tk.Canvas(
            self.root,
            width=self.screen_width,
            height=self.screen_height,
            bg=TRANSPARENT_COLOR,
            highlightthickness=0,
        )

        self.canvas.pack(
            fill="both",
            expand=True,
        )

        self.figure_origin = (
            self.screen_width / 2,
            self.screen_height / 2,
        )

        self.target_positions: tuple[
            tuple[float, float],
            ...
        ] = ()

        self.celebration_job: str | None = None
        self.respawn_job: str | None = None
        self.tray_poll_job: str | None = None

        self.tray_icon = None

        self.tray_actions: queue.Queue[
            Callable[[], None]
        ] = queue.Queue()

        self.root.bind(
            "<Escape>",
            self.close,
        )

        self.root.bind(
            "<Key-r>",
            self.respawn,
        )

        self.root.bind(
            "<Key-R>",
            self.respawn,
        )

        self.canvas.bind(
            "<Button-1>",
            self.handle_click,
        )

        self.spawn_figure()
        self.start_tray_icon()
        self.schedule_tray_poll()

    # ------------------------------------------------------------------
    # Figure positioning
    # ------------------------------------------------------------------

    def choose_figure_origin(
        self,
    ) -> tuple[float, float]:
        """Return a random origin that keeps the figure on screen."""
        half_width = self.figure.width / 2
        half_height = self.figure.height / 2

        min_x = int(
            SCREEN_MARGIN + half_width
        )

        max_x = int(
            self.screen_width
            - SCREEN_MARGIN
            - half_width
        )

        min_y = int(
            SCREEN_MARGIN + half_height
        )

        max_y = int(
            self.screen_height
            - SCREEN_MARGIN
            - half_height
        )

        origin_x = (
            self.screen_width / 2
            if min_x >= max_x
            else random.randint(
                min_x,
                max_x,
            )
        )

        origin_y = (
            self.screen_height / 2
            if min_y >= max_y
            else random.randint(
                min_y,
                max_y,
            )
        )

        return origin_x, origin_y

    # ------------------------------------------------------------------
    # Figure drawing
    # ------------------------------------------------------------------

    def spawn_figure(self) -> None:
        """Clear the overlay and draw the figure at a random position."""
        self.respawn_job = None

        if not self.enabled:
            return

        self.clear_canvas()

        origin_x, origin_y = self.choose_figure_origin()

        self.figure_origin = (
            origin_x,
            origin_y,
        )

        self.target_positions = tuple(
            (
                origin_x + target_x,
                origin_y + target_y,
            )
            for target_x, target_y in self.figure.targets
        )

        for point in self.figure.points:
            self.draw_dot(
                origin_x + point.x,
                origin_y + point.y,
                self.get_point_color(point),
            )

    def get_point_color(
        self,
        point: FigurePoint,
    ) -> str:
        """Return the display colour for ``point``."""
        if DEBUG_SHOW_TARGETS and point.is_target:
            return DEBUG_TARGET_COLOR

        if point.point_type == "special":
            return self.figure.special_color

        return DOT_COLOR

    def draw_dot(
        self,
        x: float,
        y: float,
        color: str,
    ) -> int:
        """Draw one circular figure point and return its canvas ID."""
        return self.canvas.create_oval(
            x - DOT_RADIUS,
            y - DOT_RADIUS,
            x + DOT_RADIUS,
            y + DOT_RADIUS,
            fill=color,
            outline="",
        )

    def clear_canvas(self) -> None:
        """Remove everything currently displayed on the overlay."""
        self.canvas.delete("all")
        self.target_positions = ()

    # ------------------------------------------------------------------
    # Target detection
    # ------------------------------------------------------------------

    def find_clicked_target(
        self,
        click_position: tuple[float, float],
    ) -> tuple[float, float] | None:
        """Return the closest target hit by ``click_position``."""
        click_x, click_y = click_position

        closest_target = None
        closest_distance_squared = TARGET_HIT_RADIUS_SQUARED

        for target_x, target_y in self.target_positions:
            dx = click_x - target_x
            dy = click_y - target_y

            distance_squared = (
                dx * dx
                + dy * dy
            )

            if distance_squared <= closest_distance_squared:
                closest_target = (
                    target_x,
                    target_y,
                )

                closest_distance_squared = distance_squared

        return closest_target

    def handle_click(
        self,
        event: tk.Event,
    ) -> None:
        """Handle a mouse click and trigger success for a target hit."""
        if not self.enabled:
            return

        target = self.find_clicked_target(
            (
                event.x,
                event.y,
            )
        )

        if target is None:
            return

        self.success(
            target[0],
            target[1],
        )

    # ------------------------------------------------------------------
    # Celebration
    # ------------------------------------------------------------------

    def success(
        self,
        x: float,
        y: float,
    ) -> None:
        """Remove the figure and start the success celebration."""
        self.cancel_pending_jobs()
        self.clear_canvas()

        particles = self.create_celebration_particles(
            x,
            y,
        )

        self.canvas.create_text(
            x,
            y - 60,
            text=self.figure.message,
            fill="white",
            font=(
                "Segoe UI",
                24,
                "bold",
            ),
        )

        self.animate_celebration(
            particles=particles,
            elapsed_ms=0,
        )

    def create_celebration_particles(
        self,
        x: float,
        y: float,
    ) -> list[Particle]:
        """Create animated celebration particles around ``(x, y)``."""
        particles: list[Particle] = []

        colors = (
            "white",
            "yellow",
            "cyan",
            "magenta",
            "lime",
            "orange",
        )

        for _ in range(
            CELEBRATION_PARTICLE_COUNT
        ):
            angle = random.uniform(
                0,
                math.tau,
            )
            speed = random.uniform(
                2.0,
                8.0,
            )

            radius = random.randint(
                2,
                5,
            )

            item = self.canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill=random.choice(colors),
                outline="",
            )

            # Import-free equivalents of cos/sin are not desirable here,
            # so calculate using the standard math module locally.
            from math import cos, sin

            particles.append(
                Particle(
                    item=item,
                    dx=cos(angle) * speed,
                    dy=sin(angle) * speed,
                )
            )

        return particles

    def animate_celebration(
        self,
        particles: list[Particle],
        elapsed_ms: int,
    ) -> None:
        """Advance the success animation by one frame."""
        if not self.enabled:
            self.celebration_job = None
            return

        if elapsed_ms >= CELEBRATION_DURATION_MS:
            self.celebration_job = None

            self.clear_canvas()

            self.respawn_job = self.root.after(
                RESPAWN_DELAY_MS,
                self.spawn_figure,
            )

            return

        for particle in particles:
            self.canvas.move(
                particle.item,
                particle.dx,
                particle.dy,
            )

            particle.dy += 0.12
            particle.dx *= 0.99

        self.celebration_job = self.root.after(
            ANIMATION_FRAME_MS,
            self.animate_celebration,
            particles,
            elapsed_ms + ANIMATION_FRAME_MS,
        )

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    def set_enabled(
        self,
        enabled: bool,
    ) -> None:
        """Set whether the trainer is active."""
        if self.closing or self.enabled == enabled:
            return

        self.enabled = enabled

        self.cancel_pending_jobs()
        self.clear_canvas()

        if enabled:
            self.root.deiconify()
            self.root.lift()

            self.root.attributes(
                "-topmost",
                True,
            )

            self.spawn_figure()

        else:
            self.root.withdraw()

        self.update_tray_menu()

    def toggle_enabled(self) -> None:
        """Toggle the trainer's enabled state."""
        self.set_enabled(
            not self.enabled
        )

    # ------------------------------------------------------------------
    # Figure reload
    # ------------------------------------------------------------------

    def reload_figure(self) -> None:
        """Reload and atomically replace the current figure definition."""
        if self.closing:
            return

        try:
            new_figure = load_text_figure(
                FIGURE_FILE
            )

        except (
            OSError,
            ValueError,
        ) as error:
            self.show_error(
                "Could not reload stick_figure.txt",
                str(error),
            )
            return

        self.figure = new_figure

        self.cancel_pending_jobs()
        self.clear_canvas()

        if self.enabled:
            self.spawn_figure()

    # ------------------------------------------------------------------
    # Manual respawn
    # ------------------------------------------------------------------

    def respawn(
        self,
        _event: tk.Event | None = None,
    ) -> None:
        """Interrupt the current lifecycle and immediately respawn."""
        if not self.enabled:
            return

        self.cancel_pending_jobs()
        self.spawn_figure()

    # ------------------------------------------------------------------
    # Tkinter job management
    # ------------------------------------------------------------------

    def cancel_pending_jobs(self) -> None:
        """Cancel celebration and delayed-respawn callbacks."""
        self.celebration_job = self.cancel_job(
            self.celebration_job
        )

        self.respawn_job = self.cancel_job(
            self.respawn_job
        )

    def cancel_job(
        self,
        job: str | None,
    ) -> None:
        """Cancel one Tkinter ``after`` job if it exists."""
        if job is None:
            return None

        try:
            self.root.after_cancel(job)
        except tk.TclError:
            pass

        return None

    # ------------------------------------------------------------------
    # Tray
    # ------------------------------------------------------------------

    def start_tray_icon(self) -> None:
        """Create the system tray icon on a daemon thread."""
        self.tray_icon = pystray.Icon(
            "cursor_accuracy_trainer",
            create_tray_image(),
            "Cursor Accuracy Trainer",
            self.create_tray_menu(),
        )

        threading.Thread(
            target=self.tray_icon.run,
            daemon=True,
            name="TrayIcon",
        ).start()

    def create_tray_menu(self):
        """Return the system tray menu."""
        return pystray.Menu(
            pystray.MenuItem(
                "Enabled",
                self.tray_toggle_enabled,
                checked=lambda _item: self.enabled,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Reload stick_figure.txt",
                self.tray_reload_figure,
            ),
            pystray.MenuItem(
                "Respawn",
                self.tray_respawn,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Exit",
                self.tray_exit,
            ),
        )

    def queue_tray_action(
        self,
        action: Callable[[], None],
    ) -> None:
        """Queue a tray action for Tkinter's main thread."""
        if not self.closing:
            self.tray_actions.put(action)

    def schedule_tray_poll(self) -> None:
        """Schedule the next check for queued tray actions."""
        if self.closing:
            return

        self.tray_poll_job = self.root.after(
            TRAY_QUEUE_CHECK_MS,
            self.process_tray_actions,
        )

    def process_tray_actions(self) -> None:
        """Execute queued tray actions on Tkinter's main thread."""
        self.tray_poll_job = None

        if self.closing:
            return

        while True:
            try:
                action = self.tray_actions.get_nowait()
            except queue.Empty:
                break

            action()

        self.schedule_tray_poll()

    def tray_toggle_enabled(
        self,
        _icon,
        _item,
    ) -> None:
        """Queue an enabled-state toggle from the tray."""
        self.queue_tray_action(
            self.toggle_enabled
        )

    def tray_reload_figure(
        self,
        _icon,
        _item,
    ) -> None:
        """Queue a figure reload from the tray."""
        self.queue_tray_action(
            self.reload_figure
        )

    def tray_respawn(
        self,
        _icon,
        _item,
    ) -> None:
        """Queue an immediate respawn from the tray."""
        self.queue_tray_action(
            self.respawn
        )

    def tray_exit(
        self,
        _icon,
        _item,
    ) -> None:
        """Queue application shutdown from the tray."""
        self.queue_tray_action(
            self.close
        )

    def update_tray_menu(self) -> None:
        """Refresh dynamic tray-menu state."""
        if self.tray_icon is None:
            return

        try:
            self.tray_icon.update_menu()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------

    def show_error(
        self,
        title: str,
        text: str,
    ) -> None:
        """Display an application error dialog."""
        was_hidden = not self.enabled

        if was_hidden:
            self.root.deiconify()

        messagebox.showerror(
            title,
            text,
            parent=self.root,
        )

        if was_hidden:
            self.root.withdraw()

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def close(
        self,
        _event: tk.Event | None = None,
    ) -> None:
        """Stop pending work, close the tray icon, and exit."""
        if self.closing:
            return

        self.closing = True

        self.cancel_pending_jobs()

        if self.tray_poll_job is not None:
            try:
                self.root.after_cancel(
                    self.tray_poll_job
                )
            except tk.TclError:
                pass

            self.tray_poll_job = None

        if self.tray_icon is not None:
            self.tray_icon.stop()
            self.tray_icon = None

        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def run(self) -> None:
        """Run the Tkinter event loop."""
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Startup errors
# ---------------------------------------------------------------------------


def show_startup_error(
    error: Exception,
) -> None:
    """Display an error encountered before the application starts."""
    root = tk.Tk()
    root.withdraw()

    messagebox.showerror(
        "Cursor Accuracy Trainer",
        str(error),
        parent=root,
    )

    root.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Load the configured figure and start the trainer."""
    try:
        figure = load_text_figure(
            FIGURE_FILE
        )

    except (
        OSError,
        ValueError,
    ) as error:
        show_startup_error(error)
        return

    CursorTrainer(
        figure
    ).run()


if __name__ == "__main__":
    main()