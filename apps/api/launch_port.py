"""Port choice for the launchers (启动游戏.bat / 启动游戏.command).

Prints one line: `running <port>` when this game already answers on a port in the range (the
launcher then just opens it, so two servers never share one save folder), `free <port>` for the
first free port from 8000 on, or `none` when every port in the range is taken.
Usage: python launch_port.py [first_port] [last_port]
"""
import json
import socket
import sys
import urllib.request

FIRST_PORT = 8000
LAST_PORT = 8099
HOST = "127.0.0.1"

# Health checks go straight to this machine, never through a configured proxy.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _listening(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        return probe.connect_ex((HOST, port)) == 0


def _bindable(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((HOST, port))
        except OSError:
            return False
        return True


def _is_this_game(port):
    try:
        with _opener.open(f"http://{HOST}:{port}/api/health", timeout=1) as response:
            health = json.load(response)
    except (OSError, ValueError):
        return False
    return (isinstance(health, dict) and health.get("app_id") == "fantasy-simulator" and
            health.get("api_version") == "1")


def find_port(first=FIRST_PORT, last=LAST_PORT):
    """("running", port) if the game is already up, ("free", port), or ("none", None)."""
    free = None
    for port in range(first, last + 1):
        if _listening(port):
            if _is_this_game(port):
                return "running", port
        elif free is None and _bindable(port):
            free = port
    return ("free", free) if free is not None else ("none", None)


def main(argv):
    first = int(argv[1]) if len(argv) > 1 else FIRST_PORT
    last = int(argv[2]) if len(argv) > 2 else LAST_PORT
    mode, port = find_port(first, last)
    print(mode if port is None else f"{mode} {port}")
    return 0 if port is not None else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
