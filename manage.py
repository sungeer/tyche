import sys
import os
import importlib
import pkgutil


def get_all_commands():
    import src.commands as pkg
    return [name for _, name, _ in pkgutil.iter_modules(pkg.__path__)]


def print_usage(prog):
    print(f'Usage: python {prog} <command> [options]\n')
    print('Available commands:')
    for name in sorted(get_all_commands()):
        try:
            mod = importlib.import_module(f'src.commands.{name}')
            cmd = mod.Command()
            print(f'  {name:<20} {cmd.help}')
        except (Exception,):
            print(f'  {name}')


def main():
    from src.core.logger import setup_logger
    setup_logger()

    prog = os.path.basename(sys.argv[0])

    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help', 'help'):
        print_usage(prog)
        return

    command_name = sys.argv[1]

    try:
        mod = importlib.import_module(f'src.commands.{command_name}')
        command = mod.Command()
    except (ImportError, AttributeError):
        print(f"Unknown command: '{command_name}'")
        print(f"Run 'python {prog} help' to see available commands.")
        sys.exit(1)

    parser = command.create_parser(prog, command_name)
    options = parser.parse_args(sys.argv[2:])
    command.execute(**vars(options))


if __name__ == '__main__':
    main()
