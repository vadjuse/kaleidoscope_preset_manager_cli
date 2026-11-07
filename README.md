# Kaleidoscope Manager CLI

A command-line tool for managing presets and firmware of the **Vadjuse Kaleidoscope** synthesizer.

Export presets from your synthesizer, organize a local preset library, import presets into any device slot, and update firmware — all from a single terminal interface.

**Experimental software.** The tool directly modifies files on the synthesizer. Keep backups of your presets before using it.

## Features

- **Preset export** — transfer presets from Kaleidoscope to your computer.
- **Preset import** — install local presets into any device slot (0–127).
- **Preset library** — maintain a local collection of presets.
- **Firmware download** — download available firmware builds from GitHub.
- **Firmware installation** — transfer firmware to the synthesizer.
- **Device inspection** — browse files on the synthesizer filesystem.
- **Cleanup** — remove temporary transfer files.
- **TAB completion** — autocomplete commands, preset names and firmware filenames.
- **Command history** — restore previously entered commands between sessions.

## Requirements

- macOS
- Python 3
- USB-connected Kaleidoscope synthesizer

No external Python packages required.

## Installation

Clone the repository:

```bash
git clone https://github.com/vadjuse/kaleidoscope-manager.git
cd kaleidoscope-manager
```

Run:

```bash
python3 ks_pres_cli.py
```

The manager automatically detects a connected Kaleidoscope on startup.

## Commands

| Command | Description |
|:---|:---|
| `help` | Show available commands |
| `connect` | Detect and connect to Kaleidoscope |
| `ls` | List files on the device |
| `export N` | Prepare export of preset from slot N |
| `export save` | Save exported presets to computer |
| `import NAME SLOT` | Import a local preset into a device slot |
| `fw get` | Download available firmware from GitHub |
| `fw send NAME` | Send firmware to Kaleidoscope |
| `clean` | Remove temporary transfer files |
| `eject` | Safely eject Kaleidoscope |
| `quit` | Exit the manager |

## Preset management

### Export

Export a preset from a specific device slot:

```text
> export 3
Export request created: exp003.bin
Export command sent to device.
```

After the synthesizer completes the export, save the preset locally:

```text
> export save
Exported: spacehunt
Export complete: 1 presets.
```

Presets are stored in the local `presets/` directory.

If a preset with the same name already exists, a numeric suffix is added automatically to prevent overwriting.

### Import

Import a local preset into a specific device slot:

```text
> import spacehunt 11
Importing preset 'spacehunt' to slot 11...
Import completed: imp011.bin
Import command sent to device.
```

Usage:

```text
import PRESET_NAME SLOT_NUM
```

Valid slots: `0–127`.

## Firmware management

### Download firmware

Download all available `.bin` firmware files from the latest firmware directory on GitHub:

```text
> fw get
```

Files are saved to `firmwares/`. Existing files are skipped and not overwritten.

### Send firmware

Transfer a firmware file to Kaleidoscope:

```text
> fw send firmware_v84
```

The manager copies the firmware to the device as `blink.bin` and updates `kaleidoscope.json` with the firmware name.

The synthesizer handles the actual installation.

## Device management

### List files

```text
> ls
```

Displays files on the device and identifies known filesystem entries:

| File | Description |
|:---|:---|
| `exp.bin` | Export command marker |
| `imp.bin` | Import command marker |
| `expNNN.bin` | Export request or exported preset |
| `impNNN.bin` | Preset prepared for import |
| `blink.bin` | Firmware waiting for installation |
| `kaleidoscope.json` | Device configuration |

### Cleanup

```text
> clean
```

Removes temporary preset transfer files (`exp.bin`, `expc.bin`, `expNNN.bin` and `impNNN.bin`).

### Safely eject

```text
> eject
```

Safely ejects Kaleidoscope using macOS `diskutil`.

## Local directory structure

```text
kaleidoscope-manager/
├── ks_pres_cli.py
├── .history
├── presets/
│   ├── spacehunt
│   ├── neurokick
│   └── ...
└── firmwares/
    ├── firmware_v84.bin
    └── ...
```

Preset files are stored without extensions. Their filenames correspond to the preset names stored inside the binary data.

## Interface

The manager supports:

- `TAB` — command and filename completion.
- `↑` / `↓` — navigate command history.
- Command history is saved between sessions.

## Limitations

- Currently supports macOS and the `/Volumes/KLRU` mount point.
- Preset files must contain at least 157 bytes.
- Preset parameter editing is not supported.
- Firmware and preset installation are handled by the synthesizer.
- Device communication relies on filesystem markers rather than a direct serial connection.

