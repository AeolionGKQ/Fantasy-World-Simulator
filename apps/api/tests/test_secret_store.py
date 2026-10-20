"""Key storage on macOS (login Keychain via the `security` tool), exercised with a fake tool."""
import base64
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR.parent))
from api.database import SecretStore  # noqa: E402


class FakeSecurity:
    """Stands in for /usr/bin/security: generic passwords kept in a dict."""

    def __init__(self):
        self.items = {}
        self.argv = []
        self.broken = False

    def __call__(self, args, stdin=None):
        self.argv.append(list(args))
        if self.broken:
            raise subprocess.CalledProcessError(1, ["security", *args])
        if args == ["-i"]:
            for line in (stdin or "").splitlines():
                self.run(shlex.split(line))
            return ""
        return self.run(list(args))

    def run(self, args):
        command, options = args[0], args[1:]
        values = {options[i]: options[i + 1] for i in range(len(options) - 1) if options[i].startswith("-")}
        key = (values.get("-s"), values.get("-a"))
        if command == "add-generic-password":
            self.items[key] = values["-w"]
            return ""
        if key not in self.items:
            raise subprocess.CalledProcessError(44, ["security", command])
        if command == "find-generic-password":
            return self.items[key] + "\n"
        if command == "delete-generic-password":
            del self.items[key]
            return ""
        raise AssertionError(command)


class KeychainSecretStoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / ".data" / "secrets.dat"
        self.security = FakeSecurity()

    def store(self, path=None):
        store = SecretStore(path or self.path, backend="keychain")
        store._security = self.security
        return store

    def test_key_lives_in_the_keychain_and_survives_a_restart(self):
        key = "sk-测试-key with spaces;$`\"'"
        store = self.store()
        self.assertEqual("macos_keychain", store.persistence)
        self.assertTrue(store.set_api_key(key))
        self.assertEqual("keychain:v1", self.path.read_text(encoding="utf-8"))  # only a marker on disk
        encoded = base64.b64encode(key.encode("utf-8")).decode("ascii")
        for argv in self.security.argv:  # the key is never on a command line
            self.assertNotIn(key, " ".join(argv))
            self.assertNotIn(encoded, " ".join(argv))
        self.assertEqual(key, self.store().get_api_key())  # a new process reads it back

    def test_settings_save_writes_the_keychain_only_on_commit(self):
        store = self.store()
        prepared = store.prepare_api_key("sk-prepared")
        self.assertEqual({}, self.security.items)  # a failed settings save would leave nothing behind
        self.assertTrue(store.commit_api_key(prepared))
        self.assertEqual("sk-prepared", self.store().get_api_key())

    def test_clearing_the_key_removes_the_keychain_item(self):
        store = self.store()
        store.set_api_key("sk-old")
        self.assertTrue(store.set_api_key(""))
        self.assertEqual({}, self.security.items)
        self.assertFalse(self.path.exists())
        self.assertEqual("", self.store().get_api_key())

    def test_each_install_folder_has_its_own_item(self):
        other = Path(self.temporary.name) / "other-copy" / "secrets.dat"
        self.store().set_api_key("sk-first")
        self.store(other).set_api_key("sk-second")
        self.assertEqual(2, len(self.security.items))
        self.assertEqual("sk-first", self.store().get_api_key())
        self.assertEqual("sk-second", self.store(other).get_api_key())

    def test_an_unavailable_keychain_falls_back_to_memory(self):
        self.security.broken = True
        store = self.store()
        self.assertFalse(store.set_api_key("sk-memory"))
        self.assertEqual("memory_only", store.persistence)
        self.assertEqual("sk-memory", store.get_api_key())  # still usable until restart
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
