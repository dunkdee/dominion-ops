"""The Meta credential writer and reader must resolve the same vault.

configure_meta.py writes the Meta app record; service.py reads it. They once
had different fallback defaults, so running configure_meta without
DOMINION_PUBLISHER_VAULT put credentials somewhere the service never looked --
configured and silently invisible. These tests pin them together.

Deliberately dependency-free: this imports only apps.dominion_publisher.paths,
never vault.py, so it runs even where the cryptography wheel is unusable.
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

from apps.dominion_publisher import paths

ROOT = Path(__file__).resolve().parents[1]
SERVICE_SRC = (ROOT / "apps" / "dominion_publisher" / "service.py").read_text(encoding="utf-8")
CONFIGURE_SRC = (ROOT / "apps" / "dominion_publisher" / "configure_meta.py").read_text(encoding="utf-8")


class EnvIsolatedTestCase(unittest.TestCase):
    def setEnv(self, name, value):
        previous = os.environ.get(name)
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

        def restore():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous

        self.addCleanup(restore)


class VaultResolutionTests(EnvIsolatedTestCase):
    def test_override_wins_when_set(self):
        self.setEnv(paths.ENV_VAULT_ROOT, "/srv/dominion/vault")
        self.assertEqual(paths.vault_root(), Path("/srv/dominion/vault"))

    def test_canonical_fallback_when_unset(self):
        self.setEnv(paths.ENV_VAULT_ROOT, None)
        self.setEnv(paths.ENV_STATE_ROOT, None)
        self.assertEqual(
            paths.vault_root(),
            (Path("~/.dominion/publisher") / "credential-vault").expanduser(),
        )

    def test_blank_override_falls_back_rather_than_resolving_to_cwd(self):
        # Path("") is Path("."), which would silently put the vault in the
        # working directory.
        self.setEnv(paths.ENV_VAULT_ROOT, "   ")
        self.setEnv(paths.ENV_STATE_ROOT, None)
        self.assertEqual(paths.vault_root(), paths.state_root() / "credential-vault")
        self.assertNotEqual(paths.vault_root(), Path("."))

    def test_state_root_override_moves_the_vault_with_it(self):
        self.setEnv(paths.ENV_VAULT_ROOT, None)
        self.setEnv(paths.ENV_STATE_ROOT, "/opt/pub-state")
        self.assertEqual(paths.vault_root(), Path("/opt/pub-state/credential-vault"))

    def test_user_expansion_is_applied(self):
        self.setEnv(paths.ENV_VAULT_ROOT, "~/somewhere/vault")
        resolved = paths.vault_root()
        self.assertNotIn("~", str(resolved))
        self.assertTrue(resolved.is_absolute())


class WriterAndReaderAgreeTests(EnvIsolatedTestCase):
    """The property that actually matters: one resolver, one answer."""

    def test_both_modules_resolve_through_the_shared_helper(self):
        for name, src in (("service.py", SERVICE_SRC), ("configure_meta.py", CONFIGURE_SRC)):
            with self.subTest(module=name):
                self.assertIn("from .paths import vault_root", src)
                self.assertIn("vault_root()", src)

    def test_neither_module_keeps_its_own_fallback_string(self):
        # The old divergent literals. Either one reappearing means the split is
        # back, whatever the shared helper says.
        for name, src in (("service.py", SERVICE_SRC), ("configure_meta.py", CONFIGURE_SRC)):
            with self.subTest(module=name):
                self.assertNotIn("credential-vault", src)
                self.assertNotIn("DOMINION_PUBLISHER_VAULT", src)

    def test_only_paths_module_defines_a_vault_directory_literal(self):
        """A vault *path* literal may exist in exactly one module.

        Matches a string that is the directory name itself or ends in
        "/credential-vault". It deliberately does not match vault.py's schema
        identifier "dominion-publisher-credential-vault-v1", which is a format
        version, not a location.
        """
        pattern = re.compile(r"""["'](?:[^"']*/)?credential-vault["']""")
        pkg = ROOT / "apps" / "dominion_publisher"
        offenders = sorted(
            py.name
            for py in pkg.glob("*.py")
            if pattern.search(py.read_text(encoding="utf-8"))
        )
        self.assertEqual(
            offenders, ["paths.py"],
            f"the vault directory literal must live only in paths.py; found in {offenders}",
        )

    def test_resolved_paths_are_identical_with_and_without_the_override(self):
        for override in ("/tmp/dominion-vault-under-test", None):
            with self.subTest(override=override):
                self.setEnv(paths.ENV_VAULT_ROOT, override)
                # Both modules call the same zero-argument helper, so the value
                # the writer stores to and the value the reader loads from are
                # the same object by construction.
                writer = paths.vault_root()
                reader = paths.vault_root()
                self.assertEqual(writer, reader)
                if override:
                    self.assertEqual(writer, Path(override))


if __name__ == "__main__":
    unittest.main()
