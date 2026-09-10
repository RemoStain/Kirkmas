"""
Cursor Accuracy Trainer

Displays a figure loaded from a text file on a transparent desktop overlay.

Figure file characters:
    O = normal visible dot
    X = target dot
      = empty space

Multiple X characters may be used in a single figure. Clicking any target
successfully completes the current figure.

Controls:
    R       Immediately respawn the figure.
    Esc     Close the program.
"""

from __future__ import annotations

import math
import random
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FIGURE_FILE = Path("figure.txt")

SUCCESS_MESSAGE = "Merry Kirkmas!"

# Distance, in pixels, between characters in the text file.
POINT_SPACING = 12

# Radius of each visible point.
DOT_RADIUS = 4

# Clickable radius around each target.
TARGET_HIT_RADIUS = 8

# Figure placement margin from the screen edges.
SCREEN_MARGIN = 100

# Celebration settings.
CELEBRATION_PARTICLE_COUNT = 40
CELEBRATION_DURATION_MS = 1200
RESPAWN_DELAY_MS = 1500

# Transparent overlay configuration.
TRANSPARENT_COLOR = "#010101"
DOT_COLOR = "white"

# Set to True while creating/testing figure files.
DEBUG_SHOW_TARGETS = False
DEBUG_TARGET_COLOR = "red"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FigurePoint:
    """One point in a text-defined figure."""

    x: float
    y: float
    is_target: bool = False


# ---------------------------------------------------------------------------
# Figure loading
# ---------------------------------------------------------------------------

def load_text_figure(
    file_path: Path,
    spacing: int = POINT_SPACING,
) -> list[FigurePoint]:
    """
    Load a figure from a text file.

    Supported characters:
        O = normal point
        X = target point
          = empty space

    Args:
        file_path:
            Text file containing the figure.

        spacing:
            Pixel distance between character positions.

    Returns:
        A centered list of FigurePoint objects.

    Raises:
        FileNotFoundError:
            If the figure file does not exist.

        ValueError:
            If the figure contains no points or no targets.
    """
    if not file_path.exists():
        raise FileNotFoundError(
            f"Figure file not found: {file_path.resolve()}"
        )

    lines = file_path.read_text(encoding="utf-8").splitlines()

    points: list[FigurePoint] = []

    for row, line in enumerate(lines):
        for column, character in enumerate(line):
            if character not in {"O", "X"}:
                continue

            points.append(
                FigurePoint(
                    x=column * (spacing / 2),
                    y=row * spacing,
                    is_target=character == "X",
                )
            )

    if not points:
        raise ValueError(
            f"{file_path} does not contain any O or X characters."
        )

    if not any(point.is_target for point in points):
        raise ValueError(
            f"{file_path} does not contain any targets. "
            "Add at least one X."
        )

    return center_figure(points)


def center_figure(
    points: list[FigurePoint],
) -> list[FigurePoint]:
    """Center a figure around coordinate (0, 0)."""
    min_x = min(point.x for point in points)
    max_x = max(point.x for point in points)

    min_y = min(point.y for point in points)
    max_y = max(point.y for point in points)

    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2

    return [
        FigurePoint(
            x=point.x - center_x,
            y=point.y - center_y,
            is_target=point.is_target,
        )
        for point in points
    ]


def get_figure_size(
    points: list[FigurePoint],
) -> tuple[float, float]:
    """Return the width and height occupied by a figure."""
    min_x = min(point.x for point in points)
    max_x = max(point.x for point in points)

    min_y = min(point.y for point in points)
    max_y = max(point.y for point in points)

    return (
        max_x - min_x,
        max_y - min_y,
    )


# ---------------------------------------------------------------------------
# General utilities
# ---------------------------------------------------------------------------

def distance_between(
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    """Return the Euclidean distance between two coordinates."""
    return math.hypot(
        first[0] - second[0],
        first[1] - second[1],
    )


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class CursorTrainer:
    """Transparent desktop cursor-accuracy trainer."""

    def __init__(
        self,
        figure_points: list[FigurePoint],
    ) -> None:
        self.figure_points = figure_points

        self.root = tk.Tk()

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT_COLOR)

        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()

        self.root.geometry(
            f"{self.screen_width}x{self.screen_height}+0+0"
        )

        # Windows transparent background.
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

        # Current figure location.
        self.figure_origin = (
            self.screen_width / 2,
            self.screen_height / 2,
        )

        # Absolute screen coordinates of every current target.
        self.target_positions: list[tuple[float, float]] = []

        # Tkinter callback IDs.
        #
        # These are stored so pressing R can completely interrupt
        # the current success/respawn cycle.
        self.celebration_job: str | None = None
        self.respawn_job: str | None = None

        self.root.bind("<Escape>", self.close)
        self.root.bind("<Key-r>", self.respawn)
        self.root.bind("<Key-R>", self.respawn)

        self.canvas.bind(
            "<Button-1>",
            self.handle_click,
        )

        self.spawn_figure()

    # ------------------------------------------------------------------
    # Figure placement
    # ------------------------------------------------------------------

    def choose_figure_origin(
        self,
    ) -> tuple[float, float]:
        """
        Choose a random position that keeps the entire figure on screen.
        """
        figure_width, figure_height = get_figure_size(
            self.figure_points
        )

        half_width = figure_width / 2
        half_height = figure_height / 2

        minimum_x = int(
            SCREEN_MARGIN + half_width
        )

        maximum_x = int(
            self.screen_width
            - SCREEN_MARGIN
            - half_width
        )

        minimum_y = int(
            SCREEN_MARGIN + half_height
        )

        maximum_y = int(
            self.screen_height
            - SCREEN_MARGIN
            - half_height
        )

        # Fall back to screen center if the figure is too large
        # for random placement.
        if minimum_x >= maximum_x:
            origin_x = self.screen_width / 2
        else:
            origin_x = random.randint(
                minimum_x,
                maximum_x,
            )

        if minimum_y >= maximum_y:
            origin_y = self.screen_height / 2
        else:
            origin_y = random.randint(
                minimum_y,
                maximum_y,
            )

        return origin_x, origin_y

    def spawn_figure(self) -> None:
        """Clear the canvas and draw a new copy of the figure."""
        self.respawn_job = None

        self.clear_canvas()

        self.figure_origin = self.choose_figure_origin()

        origin_x, origin_y = self.figure_origin

        for point in self.figure_points:
            screen_x = origin_x + point.x
            screen_y = origin_y + point.y

            if point.is_target:
                self.target_positions.append(
                    (
                        screen_x,
                        screen_y,
                    )
                )

            color = DOT_COLOR

            if (
                DEBUG_SHOW_TARGETS
                and point.is_target
            ):
                color = DEBUG_TARGET_COLOR

            self.draw_dot(
                screen_x,
                screen_y,
                color,
            )

    def draw_dot(
        self,
        x: float,
        y: float,
        color: str,
    ) -> int:
        """Draw one circular figure point."""
        return self.canvas.create_oval(
            x - DOT_RADIUS,
            y - DOT_RADIUS,
            x + DOT_RADIUS,
            y + DOT_RADIUS,
            fill=color,
            outline="",
        )

    def clear_canvas(self) -> None:
        """Remove everything currently displayed."""
        self.canvas.delete("all")
        self.target_positions.clear()

    # ------------------------------------------------------------------
    # Target detection
    # ------------------------------------------------------------------

    def find_clicked_target(
        self,
        click_position: tuple[float, float],
    ) -> tuple[float, float] | None:
        """
        Return the target hit by a click.

        If multiple targets overlap within the hit radius, the nearest
        target is returned.
        """
        closest_target = None
        closest_distance = TARGET_HIT_RADIUS

        for target in self.target_positions:
            distance = distance_between(
                click_position,
                target,
            )

            if distance <= closest_distance:
                closest_target = target
                closest_distance = distance

        return closest_target

    def handle_click(
        self,
        event: tk.Event,
    ) -> None:
        """Check whether the click hit any target."""
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
    # Success handling
    # ------------------------------------------------------------------

    def success(
        self,
        x: float,
        y: float,
    ) -> None:
        """Remove the figure and begin the celebration animation."""
        self.cancel_pending_jobs()
        self.clear_canvas()

        particles = []

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

            particle = self.canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill=random.choice(
                    (
                        "white",
                        "yellow",
                        "cyan",
                        "magenta",
                        "lime",
                        "orange",
                    )
                ),
                outline="",
            )

            particles.append(
                {
                    "item": particle,
                    "dx": math.cos(angle) * speed,
                    "dy": math.sin(angle) * speed,
                }
            )

        message = self.canvas.create_text(
            x,
            y - 60,
            text=SUCCESS_MESSAGE,
            fill="white",
            font=(
                "Segoe UI",
                24,
                "bold",
            ),
        )

        self.animate_celebration(
            particles=particles,
            message=message,
            elapsed_ms=0,
        )

    def animate_celebration(
        self,
        particles: list[dict],
        message: int,
        elapsed_ms: int,
    ) -> None:
        """Animate particles outward from the clicked target."""
        frame_ms = 16

        if elapsed_ms >= CELEBRATION_DURATION_MS:
            self.celebration_job = None

            self.canvas.delete("all")

            self.respawn_job = self.root.after(
                RESPAWN_DELAY_MS,
                self.spawn_figure,
            )

            return

        for particle in particles:
            self.canvas.move(
                particle["item"],
                particle["dx"],
                particle["dy"],
            )

            # Simulated downward gravity.
            particle["dy"] += 0.12

            # Slight horizontal drag.
            particle["dx"] *= 0.99

        self.celebration_job = self.root.after(
            frame_ms,
            self.animate_celebration,
            particles,
            message,
            elapsed_ms + frame_ms,
        )

    # ------------------------------------------------------------------
    # Timer management
    # ------------------------------------------------------------------

    def cancel_pending_jobs(self) -> None:
        """
        Cancel all scheduled animation and respawn callbacks.

        This allows manual respawning to completely interrupt the
        previous figure's lifecycle.
        """
        if self.celebration_job is not None:
            try:
                self.root.after_cancel(
                    self.celebration_job
                )
            except tk.TclError:
                pass

            self.celebration_job = None

        if self.respawn_job is not None:
            try:
                self.root.after_cancel(
                    self.respawn_job
                )
            except tk.TclError:
                pass

            self.respawn_job = None

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def respawn(
        self,
        _event: tk.Event | None = None,
    ) -> None:
        """
        Interrupt the current lifecycle and immediately spawn a figure.
        """
        self.cancel_pending_jobs()
        self.spawn_figure()

    def close(
        self,
        _event: tk.Event | None = None,
    ) -> None:
        """Cancel pending callbacks and close the application."""
        self.cancel_pending_jobs()
        self.root.destroy()

    def run(self) -> None:
        """Start the Tkinter application."""
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Load the configured figure and start the trainer."""
    figure_points = load_text_figure(
        FIGURE_FILE
    )

    target_count = sum(
        point.is_target
        for point in figure_points
    )

    print(
        f"Loaded {len(figure_points)} points "
        f"with {target_count} targets."
    )

    CursorTrainer(
        figure_points
    ).run()


if __name__ == "__main__":
    main()