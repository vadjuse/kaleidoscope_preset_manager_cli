import readline
import atexit
import shlex
from   pathlib import Path
import re
import subprocess
import urllib.request
import json
import os
import shutil
import sys


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

#APP_DIR = Path(__file__).resolve().parent

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent

HISTORY_FILE = APP_DIR / ".history"
DEVICE_PATH = None
PRESET_DIR = APP_DIR / "presets"
FIRMWARE_DIR = APP_DIR / "firmwares"
DEVICE_CONFIG = "kaleidoscope.json"


PRESET_NAME_OFFSET = 128
PRESET_NAME_SIZE = 11
PRESET_SIZE = 157

ASCII_OFFSETS = [
    95,
    *range(48, 58),
    *range(65, 91)
]


# ---------------------------------------------------------
# COMMANDS
# ---------------------------------------------------------

COMMANDS = {
    "help":     "show available commands",
    "connect":  "detect and connect to Kaleidoscope",
    "export":   "export presets from Kaleidoscope to computer",
    "import":   "import presets from computer to Kaleidoscope",
    "fw":       "download firmware from GitHub or send it to Kaleidoscope",
    "clean":    "remove temporary files from Kaleidoscope",
    "eject":    "safely disconnect Kaleidoscope",
    "ls":       "list files on Kaleidoscope filesystem",
    "quit":     "exit manager",
}


# ---------------------------------------------------------
# AUTOCOMPLETE
# ---------------------------------------------------------

def tab_complete(text, state):
    """Автодополнение команд, имён пресетов и прошивок."""

    line = readline.get_line_buffer()
    parts = line.split()

    # Определяем позицию текущего аргумента
    if line.endswith(" "):
        arg_index = len(parts)
    else:
        arg_index = len(parts) - 1

    # Автодополнение команд
    if arg_index == 0:
        matches = [
            command
            for command in COMMANDS
            if command.startswith(text.lower())
        ]

    # Автодополнение имён пресетов
    elif parts and parts[0].lower() == "import" and arg_index == 1:
        PRESET_DIR.mkdir(exist_ok=True)

        matches = [
            file.name
            for file in sorted(PRESET_DIR.iterdir())
            if file.is_file() and file.name.startswith(text)
        ]

    # Автодополнение подкоманд firmware
    elif parts and parts[0].lower() == "fw" and arg_index == 1:
        matches = [
            command
            for command in ["get", "send"]
            if command.startswith(text.lower())
        ]

    # Автодополнение имён прошивок
    elif (
        len(parts) >= 2
        and parts[0].lower() == "fw"
        and parts[1].lower() == "send"
        and arg_index == 2
    ):
        FIRMWARE_DIR.mkdir(exist_ok=True)

        matches = [
            file.name
            for file in sorted(FIRMWARE_DIR.iterdir())
            if file.is_file()
            and file.suffix.lower() == ".bin"
            and file.name.startswith(text)
        ]

    else:
        matches = []

    return matches[state] if state < len(matches) else None

# ---------------------------------------------------------
# COMMAND HANDLERS
# ---------------------------------------------------------

def cmd_help():
    """Показать список команд."""

    print("\nДоступные команды:\n")

    for command, description in COMMANDS.items():
        print(f"  {command:<12} {description}")

    print()

def clean_apple_files(device_path):
    """Удаление служебных файлов macOS с флэшки Kaleidoscope."""

    apple_files = {
        ".Trashes",
        ".fseventsd",
        ".Spotlight-V100",
        ".DS_Store",
        ".TemporaryItems",
        ".VolumeIcon.icns",
        ".DocumentRevisions-V100",
        ".AppleDouble",
    }

    # Удаляем известные Apple-каталоги и файлы
    for name in apple_files:
        path = device_path / name

        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file():
            try:
                path.unlink()
            except OSError:
                print(f"Cannot remove: {name}")

    # Удаляем AppleDouble-файлы во всех вложенных каталогах
    for path in device_path.rglob("._*"):
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            print(f"Cannot remove: {path.name}")


def cmd_device(args):
    """Поиск подключённого Kaleidoscope."""

    global DEVICE_PATH

    DEVICE_PATH = None

    volumes = Path("/Volumes")

    for volume in volumes.iterdir():
        if volume.is_dir() and volume.name == "KLRU":
            DEVICE_PATH = volume
            print(f"Kaleidoscope found: {DEVICE_PATH}")

            clean_apple_files(DEVICE_PATH)
            print("Apple files cleaned.")

            return

    print("Kaleidoscope not found.")
    print("Please connect Kaleidoscope and run 'connect' manually.")

def get_preset_name(data):
    """Извлечь имя пресета из бинарных данных."""

    if len(data) < PRESET_NAME_OFFSET + PRESET_NAME_SIZE:
        return None

    name_bytes = data[
        PRESET_NAME_OFFSET:
        PRESET_NAME_OFFSET + PRESET_NAME_SIZE
    ]

    name = "".join(
        chr(ASCII_OFFSETS[index])
        for index in name_bytes
        if index < len(ASCII_OFFSETS)
    ).rstrip()

    return name if name else None

def cmd_ls(args):
    """Показать содержимое Kaleidoscope."""

    if args:
        print("Usage: ls")
        return

    if DEVICE_PATH is None or not DEVICE_PATH.exists():
        print("Kaleidoscope not found. Run 'connect' first.")
        return

    print(f"\nContents of Kaleidoscope ({DEVICE_PATH}):\n")
    print(f"{'FILE':<18} DESCRIPTION")
    print("-" * 65)

    files = sorted(
        (f for f in DEVICE_PATH.iterdir() if f.is_file()),
        key=lambda f: f.name.lower()
    )

    if not files:
        print("Device is empty.")
        return

    for file in files:
        filename = file.name

        if filename == "exp.bin":
            description = "Export command"

        elif filename == "imp.bin":
            description = "Import command"

        elif filename == "blink.bin":
            description = "Firmware waiting for installation"
        elif filename == "kaleidoscope.json":
            try:
                config = json.loads(file.read_text(encoding="utf-8"))
                firmware = config.get("firmware", "unknown")
                description = f"Last firmware: {firmware}"
            except (OSError, json.JSONDecodeError):
                description = "Invalid configuration"

        elif re.fullmatch(r"exp\d{3}\.bin", filename):
            try:
                name = get_preset_name(file.read_bytes())
                description = f"Export preset: {name}" if name else "Export preset: unknown name"
            except OSError:
                description = "Cannot read file"

        elif re.fullmatch(r"imp\d{3}\.bin", filename):
            try:
                name = get_preset_name(file.read_bytes())
                description = f"Import preset: {name}" if name else "Import preset: unknown name"
            except OSError:
                description = "Cannot read file"

        else:
            description = "Unknown file"

        print(f"{filename:<18} {description}")

    print()

def export_from_device():
    """Забрать экспортированные пресеты с устройства."""

    if DEVICE_PATH is None or not DEVICE_PATH.exists():
        print("Kaleidoscope not found. Run 'device' first.")
        return

    PRESET_DIR.mkdir(exist_ok=True)

    files = sorted(
        f for f in DEVICE_PATH.glob("exp*.bin")
        if re.fullmatch(r"exp\d{3}\.bin", f.name)
    )

    exported = 0

    for file in files:
        data = file.read_bytes()

        if len(data) < PRESET_SIZE:
            print(f"Invalid file: {file.name}")
            continue

        name = get_preset_name(data)

        if not name:
            print(f"Empty preset name: {file.name}")
            continue

        output_file = PRESET_DIR / name

        if output_file.exists():
            suffix = 2

            while True:
                output_file = PRESET_DIR / f"{name}_{suffix}"

                if not output_file.exists():
                    break

                suffix += 1

            print(f"Duplicate name: '{name}'. Saved as '{output_file.name}'")

        output_file.write_bytes(data)

        file.unlink()

        print(f"Exported: {output_file.name}")
        exported += 1

    # Удаляем файл команды экспорта
    exp_request = DEVICE_PATH / "exp.bin"

    if exp_request.exists():
        exp_request.unlink()
        print("Export request removed.")

    print(f"Export complete: {exported} presets.")


def prepare_export(slot_arg):
    """Создать запрос на экспорт конкретного слота."""

    if DEVICE_PATH is None or not DEVICE_PATH.exists():
        print("Kaleidoscope not found. Run 'device' first.")
        return

    if not re.fullmatch(r"\d+", slot_arg):
        print("Usage: export [0-127]")
        print("Example: export 1")
        return

    slot = int(slot_arg)

    if not 0 <= slot <= 127:
        print("Invalid slot number. Slot must be between 0 and 127.")
        return

    slot_file = DEVICE_PATH / f"exp{slot:03d}.bin"

    if slot_file.exists():
        print(f"Export request for slot {slot} already exists.")
    else:
        slot_file.touch()
        print(f"Export request created: exp{slot:03d}.bin")

    # Файл команды создаём только если его ещё нет
    exp_request = DEVICE_PATH / "exp.bin"

    if not exp_request.exists():
        exp_request.touch()
        print("Export command sent to device.")


def cmd_export(args):
    """Управление экспортом пресетов."""

    if len(args) == 1 and args[0].lower() == "save":
        export_from_device()
        return

    if len(args) not in (1, 2):
        print("Usage:")
        print("  export save       - save presets from Kaleidoscope to computer")
        print("  export N          - prepare export of slot N (0-127)")
        print("  export N M        - prepare export of slots N through M")
        return

    # Проверяем числовые аргументы
    try:
        start = int(args[0])
        end = int(args[1]) if len(args) == 2 else start
    except ValueError:
        print("Invalid slot number.")
        print("Usage: export N (0-127) or export N M (0-127)")
        return

    # Проверяем границы
    if not (0 <= start <= 127 and 0 <= end <= 127):
        print("Slot numbers must be between 0 and 127.")
        return

    # Проверяем порядок диапазона
    if start > end:
        print("Invalid range: starting slot must be less than or equal to ending slot.")
        return

    # Подготавливаем экспорт
    for slot in range(start, end + 1):

        filename = f"exp{slot:03d}.bin"
        filepath = DEVICE_PATH / filename

        if filepath.exists():
            print(f"Skipped: {filename} already exists.")
            continue

        prepare_export(str(slot))
        print(f"Export prepared: SLOT{slot:03d}")

def cmd_import(args):
    """Импорт пресета в Kaleidoscope."""

    # Проверка количества аргументов
    if len(args) != 2:
        print("Usage: import PRESET_NAME SLOT_NUM")
        return

    preset_name = args[0]
    slot_arg = args[1]

    # Проверка существования пресета
    preset_file = PRESET_DIR / preset_name

    if not preset_file.is_file() or preset_file.parent != PRESET_DIR:
        print(f"Preset '{preset_name}' not found.")
        print("Use: import PRESET_NAME SLOT_NUM")
        return

    # Проверка номера слота
    if not slot_arg.isdigit():
        print("Invalid slot number. Slot must be between 0 and 127.")
        return

    slot_num = int(slot_arg)

    if not 0 <= slot_num <= 127:
        print("Invalid slot number. Slot must be between 0 and 127.")
        return

    # Проверка подключения устройства
    if DEVICE_PATH is None or not DEVICE_PATH.exists():
        print("Kaleidoscope not found. Run 'device' first.")
        return

    # Читаем пресет
    data = preset_file.read_bytes()

    if len(data) < PRESET_SIZE:
        print(f"Invalid preset file: {preset_name}")
        return

    # Формируем имя файла для устройства
    output_name = f"imp{slot_num:03d}.bin"
    output_file = DEVICE_PATH / output_name

    print(f"Importing preset '{preset_name}' to slot {slot_num}...")

    # Записываем файл на устройство
    output_file.write_bytes(data)

    print(f"Import completed: {output_name}")

    # Отправляем команду бутлоадеру

    imp_request = DEVICE_PATH / "imp.bin"
    if imp_request.exists():
        print("Device is already ready for import.")
    else:
        imp_request.touch()
        print("Import command sent to device.")

def cmd_firmware(args):
    if not args:
        print("Использование: fw get | fw send FIRMWARE")
        return

    # FW GET
    if args[0] == "get":
        api_url = (
            "https://api.github.com/repos/vadjuse/kaleidoscope/"
            "contents/Release%20FWs/latest?ref=main"
        )

        os.makedirs(FIRMWARE_DIR, exist_ok=True)

        try:
            request = urllib.request.Request(
                api_url,
                headers={"User-Agent": "Kaleidoscope-Manager"}
            )

            with urllib.request.urlopen(request, timeout=15) as response:
                files = json.loads(response.read().decode("utf-8"))

        except Exception as e:
            print(f"Ошибка получения списка прошивок: {e}")
            return

        downloaded = 0
        skipped = 0

        for file in files:
            if file["type"] != "file" or not file["name"].lower().endswith(".bin"):
                continue

            filename = file["name"]
            local_path = FIRMWARE_DIR / filename

            if local_path.exists():
                print(f"Уже существует: {filename}")
                skipped += 1
                continue

            try:
                request = urllib.request.Request(
                    file["download_url"],
                    headers={"User-Agent": "Kaleidoscope-Manager"}
                )

                with urllib.request.urlopen(request, timeout=30) as response:
                    data = response.read()

                local_path.write_bytes(data)

                print(f"Скачано: {filename}")
                downloaded += 1

            except Exception as e:
                print(f"Ошибка скачивания {filename}: {e}")

        print(f"\nГотово. Скачано: {downloaded}, пропущено: {skipped}")
        return

    # FW SEND
    if args[0] == "send":
        if len(args) != 2:
            print("Использование: fw send FIRMWARE")
            return

        firmware_name = args[1]

        if not firmware_name.lower().endswith(".bin"):
            firmware_name += ".bin"

        firmware_path = FIRMWARE_DIR / firmware_name

        if not firmware_path.is_file():
            print(f"Прошивка не найдена: {firmware_name}")
            return

        if DEVICE_PATH is None:
            print("Устройство не подключено. Сначала выполните device.")
            return

        device_path = Path(DEVICE_PATH)

        if not device_path.is_dir():
            print("Путь к устройству недоступен.")
            return

        blink_path = device_path / "blink.bin"

        try:
            # Проверяем исходную прошивку
            source_size = firmware_path.stat().st_size

            if source_size == 0:
                print("Ошибка: исходная прошивка пустая.")
                return

            # Проверяем существующий blink.bin
            if blink_path.exists():
                if blink_path.stat().st_size == 0:
                    print("Обнаружен пустой blink.bin. Удаляем...")
                    blink_path.unlink()
                else:
                    print("На устройстве уже существует blink.bin.")
                    print("Удалите его вручную перед отправкой прошивки.")
                    return

            # Копируем прошивку
            try:
                shutil.copy2(firmware_path, blink_path)

                # Проверяем результат копирования
                if not blink_path.is_file():
                    raise IOError("Файл blink.bin не создан.")

                copied_size = blink_path.stat().st_size

                if copied_size == 0:
                    raise IOError("Скопированный файл пустой.")

                if copied_size != source_size:
                    raise IOError(
                        f"Размеры не совпадают: "
                        f"исходный {source_size}, скопированный {copied_size}"
                    )

            except Exception:
                # Удаляем результат неудачного копирования
                if blink_path.exists():
                    blink_path.unlink()
                raise

            # Читаем существующий JSON или создаём новый
            config_path = device_path / DEVICE_CONFIG

            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            else:
                config = {}

            # Записываем имя прошивки без расширения
            config["firmware"] = firmware_path.stem

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            print(f"Прошивка успешно отправлена: {firmware_name}")
            print(f"Размер: {copied_size} байт")

        except Exception as e:
            print(f"Ошибка отправки прошивки: {e}")

        return

    print("Использование: fw get | fw send FIRMWARE")


def cmd_clean(args):
    """Удалить временные файлы обмена с Kaleidoscope."""

    if args:
        print("Usage: clean")
        return

    if DEVICE_PATH is None or not DEVICE_PATH.exists():
        print("Kaleidoscope not found. Run 'device' first.")
        return

    patterns = [
        "exp.bin",
        "expc.bin",
    ]

    files_to_delete = []

    # Файлы экспорта и импорта
    for slot in range(128):
        patterns.append(f"exp{slot:03d}.bin")
        patterns.append(f"imp{slot:03d}.bin")

    for filename in patterns:
        file_path = DEVICE_PATH / filename

        if file_path.is_file():
            files_to_delete.append(file_path)

    if not files_to_delete:
        print("No temporary files found.")
        return

    deleted = 0

    for file_path in files_to_delete:
        try:
            file_path.unlink()
            deleted += 1
        except OSError as e:
            print(f"Cannot delete {file_path.name}: {e}")

    print(f"Cleanup complete. Deleted {deleted} temporary files.")

def cmd_eject(args):
    """Безопасно извлечь Kaleidoscope."""

    if args:
        print("Usage: eject")
        return

    if DEVICE_PATH is None or not DEVICE_PATH.exists():
        print("Kaleidoscope not found.")
        return

    try:
        subprocess.run(
            ["diskutil", "eject", str(DEVICE_PATH)],
            check=True
        )
        print("Kaleidoscope safely ejected.")

    except subprocess.CalledProcessError:
        print("Failed to eject Kaleidoscope.")

# ---------------------------------------------------------
# COMMAND DISPATCHER
# ---------------------------------------------------------

def execute_command(parts):

    command = parts[0].lower()
    args = parts[1:]

    handlers = {
        "help": lambda: cmd_help(),
        "connect": lambda: cmd_device(args),
        "export": lambda: cmd_export(args),
        "import": lambda: cmd_import(args),
        "fw": lambda: cmd_firmware(args),
        "clean": lambda: cmd_clean(args),
        "ls": lambda: cmd_ls(args),
        "eject": lambda: cmd_eject(args),
    }

    if command == "quit":
        return False

    handler = handlers.get(command)

    if handler is None:
        print(f"Неизвестная команда: {command}")
        print("Введите help для списка команд.")
        return True

    handler()
    return True


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    print("\nKALEIDOSCOPE MANAGER CLI")
    print("Введите help для списка команд.\n")

    # История команд
    try:
        readline.read_history_file(HISTORY_FILE)
    except FileNotFoundError:
        pass

    atexit.register(readline.write_history_file, HISTORY_FILE)

    # Initial device detection
    cmd_device([])

    # TAB autocomplete
    readline.parse_and_bind("tab: complete")
    readline.set_completer(tab_complete)
    readline.parse_and_bind("set show-all-if-ambiguous on")
    readline.parse_and_bind("set completion-query-items 0")

    # Main loop
    while True:

        try:
            command = input("> ").strip()

            if not command:
                continue

            try:
                parts = shlex.split(command)

            except ValueError as error:
                print(f"Command parsing error: {error}")
                continue

            if not execute_command(parts):
                break

        except (EOFError, KeyboardInterrupt):
            print("\nExit.")
            break

        except Exception as error:
            print(f"Error: {error}")

    print("Bye!")


if __name__ == "__main__":
    main()