"""The launchers' port choice: reuse a running game, otherwise the first free port."""
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR.parent))
from api.launch_port import find_port  # noqa: E402
from api.server import create_server  # noqa: E402


def free_block(size):
    """A run of `size` consecutive ports that are all free right now."""
    for start in range(47000, 60000, size + 1):
        sockets = []
        try:
            for port in range(start, start + size):
                probe = socket.socket()
                probe.bind(("127.0.0.1", port))
                sockets.append(probe)
            return start
        except OSError:
            continue
        finally:
            for probe in sockets:
                probe.close()
    raise RuntimeError("no free port block")


class LaunchPortTest(unittest.TestCase):
    def occupy(self, port):
        listener = socket.socket()
        listener.bind(("127.0.0.1", port))
        listener.listen()
        self.addCleanup(listener.close)

    def test_first_free_port_is_used(self):
        start = free_block(4)
        self.assertEqual(("free", start), find_port(start, start + 3))

    def test_ports_taken_by_other_programs_are_skipped(self):
        start = free_block(4)
        self.occupy(start)
        self.occupy(start + 1)
        self.assertEqual(("free", start + 2), find_port(start, start + 3))

    def test_every_port_taken(self):
        start = free_block(2)
        self.occupy(start)
        self.occupy(start + 1)
        self.assertEqual(("none", None), find_port(start, start + 1))

    def test_a_running_game_is_reused_even_after_a_free_port(self):
        start = free_block(3)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        static = Path(temporary.name) / "static"
        static.mkdir()
        (static / "index.html").write_text("<!doctype html>", encoding="utf-8")
        server = create_server("127.0.0.1", start + 1, str(Path(temporary.name) / ".data"), str(static))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(2)))
        # start is free, but the game is already up on start + 1: open that one, don't start another.
        self.assertEqual(("running", start + 1), find_port(start, start + 2))

    def test_a_second_server_cannot_take_a_port_in_use(self):
        # On Windows, SO_REUSEADDR would let it bind anyway and two servers would share one save folder.
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        static = Path(temporary.name) / "static"
        static.mkdir()
        (static / "index.html").write_text("<!doctype html>", encoding="utf-8")
        first = create_server("127.0.0.1", 0, str(Path(temporary.name) / "a"), str(static))
        self.addCleanup(first.server_close)
        with self.assertRaises(OSError):
            create_server("127.0.0.1", first.server_port, str(Path(temporary.name) / "b"), str(static)).server_close()


if __name__ == "__main__":
    unittest.main()
