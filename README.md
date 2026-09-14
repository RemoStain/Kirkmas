# Happy Kirkmas

Happy Kirkmas is a small Windows desktop cursor-accuracy trainer written in Python.

The application displays a dot-based figure on a transparent desktop overlay. Some dots are hidden targets. Clicking a target triggers a short celebration animation and a configurable success message, then the figure respawns in a new location.

The program also includes a system tray menu for enabling or disabling the trainer, reloading the figure definition, manually respawning the figure, and exiting the application.

---

## Features

* Transparent desktop overlay
* Dot-based figures loaded from a text file
* Multiple clickable targets per figure
* Configurable success message
* Configurable special-dot colour
* Built-in fallback figure
* Random figure placement
* Celebration animation
* System tray controls
* Runtime figure reload
* Standalone executable support with PyInstaller
* No external image files required for the tray icon

---

## Requirements

For development, the project requires Python and the following packages:

```text
pystray
pillow
```

Tkinter is included with standard Windows Python installations.

Install the required packages with:

```powershell
pip install pystray pillow
```

If you are building the executable, also install PyInstaller:

```powershell
pip install pyinstaller
```

---

## Running From Source

Run the main Python file normally:

```powershell
python Happy_Kirkmas.py
```

The application will look for:

```text
stick_figure.txt
```

in the same directory as `Happy_Kirkmas.py`.

If the file does not exist, the application uses its built-in fallback figure.

---

## Building the Executable

The program is designed to work as a standalone Windows executable.

Build it with:

```powershell
pyinstaller --onefile --windowed Happy_Kirkmas.py
```

The generated executable will normally be located at:

```text
dist/
└── Happy_Kirkmas.exe
```

When running as an executable, the application looks for `stick_figure.txt` in the same directory as the `.exe`.

A normal release folder therefore looks like:

```text
Happy_Kirkmas/
├── Happy_Kirkmas.exe
└── stick_figure.txt
```

The executable does not require Python to be installed on the target computer.

---

# Using the Program

When the application starts, the figure appears somewhere on the desktop.

Click one of the hidden target dots to complete the current figure.

When a target is clicked:

1. The figure disappears.
2. A celebration animation is displayed.
3. The success message appears.
4. The application waits briefly.
5. A new figure appears in a random location.

---

## Keyboard Controls

### R

Immediately respawns the figure.

This also interrupts any active celebration animation or delayed respawn.

### Esc

Closes the application.

---

# System Tray

The program creates a system tray icon when it starts.

Right-click the tray icon to access the controls.

### Enabled

Turns the desktop trainer on or off.

When disabled:

* The overlay is hidden.
* Celebration timers are stopped.
* No figure is displayed.
* The tray application remains active.

Re-enabling the trainer immediately spawns a new figure.

### Reload stick_figure.txt

Reloads the figure definition from disk.

This allows the figure, success message, and special-dot colour to be changed without restarting the program.

Reloading also interrupts the current figure lifecycle and redraws the newly loaded figure.

If `stick_figure.txt` does not exist when reload is selected, the built-in fallback figure is loaded.

### Respawn

Immediately moves the current figure to a new random position.

### Exit

Stops the tray icon and closes the application.

---

# stick_figure.txt Format

The external figure file contains both configuration and drawing data.

The format is:

```text
Line 1: success message
Line 2: special-dot hex colour
Line 3+: figure
```

Example:

```text
Congrats!
#f2c317
     OOO
    O   O
     OOO
      T
 XOOOOTOOOOX
      T
     O O
    X   X
```

---

## Supported Figure Characters

### O

Normal visible dot.

Normal dots use the application's default dot colour.

### X

Clickable target.

Targets normally look exactly like regular `O` dots.

This prevents the user from visually identifying the target.

### T

Special-colour dot.

The colour comes from line 2 of `stick_figure.txt`.

For example:

```text
#f2c317
```

### Space

Empty space.

Spaces are important because the figure parser uses character positions to determine dot coordinates.

---

# Figure Coordinate System

Each character position in the figure corresponds to a fixed amount of screen space.

The spacing is controlled by:

```python
POINT_SPACING = 12
```

For example:

```text
O O
```

places the two dots farther apart than:

```text
OO
```

because the space between them occupies its own character position.

During loading, each point is initially converted into coordinates like:

```python
x = column * POINT_SPACING
y = row * POINT_SPACING
```

The figure is then centered around coordinate:

```text
(0, 0)
```

This allows the entire figure to be moved around the screen simply by adding a new origin.

---

# Source Code Structure

The current version is contained in a single Python file.

The code is divided into several logical sections.

---

## Configuration

The configuration section contains values such as:

```python
POINT_SPACING
DOT_RADIUS
TARGET_HIT_RADIUS
SCREEN_MARGIN
CELEBRATION_PARTICLE_COUNT
CELEBRATION_DURATION_MS
RESPAWN_DELAY_MS
ANIMATION_FRAME_MS
TRAY_QUEUE_CHECK_MS
```

These values control most of the program's visual and timing behavior.

For example:

```python
DOT_RADIUS = 4
```

controls the visible size of each point.

```python
TARGET_HIT_RADIUS = 8
```

controls how close the mouse must be to a target for the click to count.

The visible radius and clickable radius are intentionally separate.

---

# Data Models

The application uses dataclasses to keep figure data structured.

## FigurePoint

```python
@dataclass(frozen=True, slots=True)
class FigurePoint:
```

A `FigurePoint` represents one dot in the figure.

It contains:

```text
x
y
point_type
```

The point type is normally one of:

```text
normal
target
special
```

The class also exposes:

```python
point.is_target
```

for checking whether the point is clickable.

The dataclass is frozen because loaded figure points should not change while the application is running.

`slots=True` is used to reduce object overhead.

---

## FigureDefinition

```python
@dataclass(frozen=True, slots=True)
class FigureDefinition:
```

A `FigureDefinition` contains everything required to render and interact with one figure.

It stores:

```text
message
special_color
points
targets
width
height
```

The figure width, height, and target coordinates are calculated when the file is loaded.

This avoids repeatedly recalculating static information every time the figure respawns.

---

## Particle

```python
@dataclass(slots=True)
class Particle:
```

A `Particle` represents one celebration particle.

It stores:

```text
item
dx
dy
```

Unlike figure data, particles are mutable because their velocity changes during animation.

---

# Figure Loading

The main loader is:

```python
load_text_figure()
```

It performs several steps:

1. Read `stick_figure.txt`, or use the fallback definition.
2. Validate the success message.
3. Validate the hex colour.
4. Parse all `O`, `X`, and `T` characters.
5. Convert character positions into coordinates.
6. Confirm that at least one target exists.
7. Center the figure.
8. Calculate its width and height.
9. Extract all target coordinates.
10. Return a complete `FigureDefinition`.

The result is effectively preprocessed and ready for repeated drawing.

---

# Built-In Fallback Figure

The application contains:

```python
DEFAULT_FIGURE
```

This is used whenever `stick_figure.txt` does not exist.

The fallback definition follows exactly the same format as the external file.

This means the built-in figure goes through the same parser and validation logic as a user-provided figure.

That keeps the behavior consistent.

---

# Figure Placement

The method:

```python
choose_figure_origin()
```

selects a random screen position.

The figure's precomputed width and height are used to prevent the drawing from being placed too close to the edges of the screen.

The margin is controlled by:

```python
SCREEN_MARGIN
```

If the figure is too large to fit within the available area, the code falls back to centering it on that axis.

---

# Drawing

The figure is drawn with a Tkinter `Canvas`.

Each point becomes a canvas oval using:

```python
self.canvas.create_oval(...)
```

The program does not use image files for the figure.

This keeps drawing simple and allows arbitrary figures to be defined with plain text.

---

## Point Colours

Point colour is determined by:

```python
get_point_color()
```

Normal points use:

```python
DOT_COLOR
```

Special points use:

```python
self.figure.special_color
```

Targets normally use the same colour as normal points.

For development, this can be changed with:

```python
DEBUG_SHOW_TARGETS = True
```

When enabled, target points are drawn using:

```python
DEBUG_TARGET_COLOR
```

This is useful when creating or testing a figure.

It should normally remain disabled for regular use.

---

# Target Detection

The absolute target positions are calculated each time the figure is spawned.

The precomputed relative coordinates are stored in:

```python
self.figure.targets
```

The spawn origin is added to each target:

```python
absolute_x = origin_x + target_x
absolute_y = origin_y + target_y
```

These positions are stored in:

```python
self.target_positions
```

---

## Hit Testing

The method:

```python
find_clicked_target()
```

checks whether a mouse click falls within the configured hit radius.

The application uses squared distance rather than calculating a full Euclidean distance.

Instead of:

```python
sqrt(dx * dx + dy * dy)
```

the code compares:

```python
dx * dx + dy * dy
```

against:

```python
TARGET_HIT_RADIUS_SQUARED
```

This avoids unnecessary square-root calculations.

For a small number of targets the performance difference is minor, but the implementation is simple and efficient.

---

# Celebration Animation

When a target is clicked:

```python
success()
```

clears the figure and generates a set of celebration particles.

The particles move using simple velocity values:

```text
dx
dy
```

Each animation frame:

```python
particle.dy += 0.12
particle.dx *= 0.99
```

This creates:

* downward acceleration
* slight horizontal drag

The animation runs at approximately 30 frames per second:

```python
ANIMATION_FRAME_MS = 33
```

This is intentionally lower than 60 FPS to reduce unnecessary CPU work while remaining visually smooth.

---

# Timed Respawning

After the celebration completes, the application schedules a respawn using:

```python
self.root.after(...)
```

The callback ID is stored in:

```python
self.respawn_job
```

The active celebration callback is stored in:

```python
self.celebration_job
```

These IDs are important because they allow the current lifecycle to be cancelled.

For example, pressing `R` calls:

```python
cancel_pending_jobs()
```

before spawning a new figure.

This prevents an old callback from later deleting or replacing the manually spawned figure.

---

# Tray Architecture

Tkinter and `pystray` do not run on the same thread.

Tkinter expects GUI operations to occur on its main thread.

The tray icon therefore runs on a separate daemon thread:

```python
threading.Thread(
    target=self.tray_icon.run,
    daemon=True,
)
```

Tray callbacks do not directly modify Tkinter.

Instead, they place callable actions into:

```python
self.tray_actions
```

which is a:

```python
queue.Queue
```

Tkinter periodically processes the queue using:

```python
process_tray_actions()
```

This avoids modifying Tkinter widgets directly from the tray thread.

---

# Reloading Figures

The figure can be replaced while the program is running.

The reload method calls:

```python
new_figure = load_text_figure(FIGURE_FILE)
```

Only after the new figure has successfully loaded and validated does the application assign:

```python
self.figure = new_figure
```

This means the old valid figure remains available if the new file contains an error.

The entire `FigureDefinition` is replaced at once instead of replacing individual properties separately.

---

# Application Paths

The application needs to behave differently when running:

```text
Happy_Kirkmas.py
```

and when running:

```text
Happy_Kirkmas.exe
```

The function:

```python
get_application_directory()
```

checks:

```python
getattr(sys, "frozen", False)
```

When packaged by PyInstaller, the directory is taken from:

```python
sys.executable
```

During normal Python development, the directory is taken from:

```python
__file__
```

This allows the same code to locate `stick_figure.txt` correctly in both environments.

---

# Error Handling

Invalid figure files are rejected before replacing the active figure.

Common validation errors include:

* missing success message
* invalid colour
* empty figure
* no target points

The hex colour must use the format:

```text
#RRGGBB
```

For example:

```text
#ffffff
#f2c317
#00ff00
```

A value such as:

```text
red
```

or:

```text
#fff
```

is not accepted by the current parser.

---

# Developing New Figures

During development, create or edit:

```text
stick_figure.txt
```

beside the Python file.

A useful workflow is:

1. Set:

```python
DEBUG_SHOW_TARGETS = True
```

2. Run the application.
3. Edit the figure file.
4. Use **Reload stick_figure.txt** from the tray.
5. Check target positioning.
6. Continue editing and reloading.
7. Set `DEBUG_SHOW_TARGETS` back to `False` before building the release.

There is no need to restart the application between figure edits.

---

# Figure Design Guidelines

Because each character occupies a fixed grid position, monospaced text is easiest to work with.

For example:

```text
    O
   O O
  O   O
 X     X
```

is preferable to editing the file in an application that automatically converts spaces or uses proportional formatting.

A plain text editor or source-code editor is recommended.

Do not use tabs for figure positioning unless you deliberately want tab expansion to affect the layout.

Spaces are more predictable.

---

# Development Setup

A basic development environment can be created with:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install pystray pillow pyinstaller
```

Run the application:

```powershell
python Happy_Kirkmas.py
```

---

# Git Repository

Generated build files should normally not be committed.

A suitable `.gitignore` includes:

```gitignore
__pycache__/
*.pyc

.venv/

build/
dist/
*.spec
```

The source file and `stick_figure.txt` should remain in the repository.

Compiled releases can be distributed through GitHub Releases.

---

# Creating a Release Build

Build the executable with:

```powershell
pyinstaller --onefile --windowed Happy_Kirkmas.py
```

After the build completes:

```text
dist/
└── Happy_Kirkmas.exe
```

Place the executable and figure file together:

```text
Happy_Kirkmas/
├── Happy_Kirkmas.exe
└── stick_figure.txt
```

These can then be packaged:

```powershell
Compress-Archive `
    -Path .\dist\Happy_Kirkmas.exe, .\stick_figure.txt `
    -DestinationPath .\Happy_Kirkmas.zip
```

The ZIP can be attached to a GitHub Release.

---

# Dependencies

The application uses:

### tkinter

Desktop overlay, drawing, timers, keyboard controls, and message dialogs.

### pystray

Windows system tray integration.

### Pillow

Creates the tray icon image programmatically.

### dataclasses

Structures figure and particle state.

### pathlib

Handles script and executable paths.

### queue

Passes tray actions safely to Tkinter.

### threading

Runs the tray icon separately from Tkinter.

### random

Randomizes figure placement and celebration particles.

### sys

Detects packaged executable execution.

No external graphics files are required by the application itself.
