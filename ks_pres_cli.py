import readline
import atexit
import shlex
from pathlib import Path
import re


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

APP_DIR = Path(__file__).resolve().parent
HISTORY_FILE = APP_DIR / ".history"
DEVICE_PATH = None
PRESET_DIR = APP_DIR / "presets"


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
    "help": "Показать список команд",
    "device": "Найти подключённый Kaleidoscope",
    "export": "Экспортировать пресеты из Kaleidoscope",
    "import": "Импортировать пресеты в Kaleidoscope",
    "firmware": "Проверить или обновить прошивку",
    "clean": "Удалить временные файлы обмена",
    "quit": "Выход",
}


# ---------------------------------------------------------
# AUTOCOMPLETE
# ---------------------------------------------------------

def tab_complete(text, state):
    """Автодополнение команд и имён пресетов."""

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


def cmd_device(args):
    """Поиск подключённого Kaleidoscope."""

    global DEVICE_PATH

    DEVICE_PATH = None

    volumes = Path("/Volumes")

    for volume in volumes.iterdir():
        if volume.is_dir() and volume.name == "KLRU":
            DEVICE_PATH = volume
            print(f"Kaleidoscope found: {DEVICE_PATH}")
            return

    print("Kaleidoscope not found.")
    print("Please connect Kaleidoscope and run 'device' manually.")


def cmd_export(args):
    """Экспорт имён пресетов."""

    if DEVICE_PATH is None or not DEVICE_PATH.exists():
        print("Kaleidoscope not found. Run 'device' first.")
        return

    preset_dir = PRESET_DIR
    preset_dir.mkdir(exist_ok=True)

    files = sorted(
    f for f in DEVICE_PATH.glob("exp*.bin")
    if re.fullmatch(r"exp\d{3}\.bin", f.name)
)

    if not files:
        print("No presets found.")
        return

    exported = 0

    for file in files:
        data = file.read_bytes()

        if len(data) < PRESET_SIZE:
            print(f"Invalid file: {file.name}")
            continue

        name_bytes = data[
            PRESET_NAME_OFFSET:
            PRESET_NAME_OFFSET + PRESET_NAME_SIZE
        ]

        name = "".join(
            chr(ASCII_OFFSETS[index])
            for index in name_bytes
            if index < len(ASCII_OFFSETS)
        ).rstrip()


        if not name:
            print(f"Empty preset name: {file.name}")
            continue

        output_file = preset_dir / name

        if output_file.exists():
            suffix = 2

            while True:
                output_file = preset_dir / f"{name}_{suffix}"

                if not output_file.exists():
                    break

                suffix += 1

            print(f"Duplicate name: '{name}'. Saved as '{output_file.name}'")

        output_file.write_bytes(data)
        # Удаляем исходный файл только после успешного копирования
        file.unlink()

        print(f"Exported: {output_file.name}")
        exported += 1

    exp_request = DEVICE_PATH / "exp.bin"

    if exp_request.exists():
        exp_request.rename(DEVICE_PATH / "expc.bin")
        print("Export completed. Device notified.")

    print(f"Export complete: {exported} presets.")


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
    print("Работа с прошивкой пока не реализована.")


def cmd_clean(args):
    print("Очистка временных файлов пока не реализована.")


# ---------------------------------------------------------
# COMMAND DISPATCHER
# ---------------------------------------------------------

def execute_command(parts):

    command = parts[0].lower()
    args = parts[1:]

    handlers = {
        "help": lambda: cmd_help(),
        "device": lambda: cmd_device(args),
        "export": lambda: cmd_export(args),
        "import": lambda: cmd_import(args),
        "firmware": lambda: cmd_firmware(args),
        "clean": lambda: cmd_clean(args),
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
                print(f"Ошибка разбора команды: {error}")
                continue

            if not execute_command(parts):
                break

        except (EOFError, KeyboardInterrupt):
            print("\nВыход.")
            break

        except Exception as error:
            print(f"Ошибка: {error}")

    print("До свидания!")


if __name__ == "__main__":
    main()