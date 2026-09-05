from __future__ import annotations

from pathlib import Path

from buddy_core.core import authorization as auth


def test_copied_buddy_home_is_not_treated_as_repository_checkout(tmp_path):
    home = tmp_path / "home"
    fake_source = home / "buddy_core" / "core" / "authorization.py"
    fake_source.parent.mkdir(parents=True)
    fake_source.write_text("# copied runtime\n", encoding="utf-8")
    (home / ".github").mkdir()

    assert auth._detect_checkout_root(fake_source) is None


def test_real_source_snapshot_marker_set_is_detected(tmp_path):
    root = tmp_path / "snapshot"
    fake_source = root / "buddy_core" / "core" / "authorization.py"
    fake_source.parent.mkdir(parents=True)
    fake_source.write_text("# source snapshot\n", encoding="utf-8")
    for marker in (".github", "governance", "tests"):
        (root / marker).mkdir()

    assert auth._detect_checkout_root(fake_source) == root.resolve()


def test_machine_local_default_key_path_remains_outside_copied_source(tmp_path):
    home = tmp_path / "home"
    copied_source = home / "buddy_core" / "core" / "authorization.py"
    copied_source.parent.mkdir(parents=True)
    copied_source.write_text("# copied runtime\n", encoding="utf-8")
    (home / ".github").mkdir()

    checkout = auth._detect_checkout_root(copied_source)
    machine_local = home / ".dominion" / "authorization" / "ledger_hmac.key"

    assert checkout is None
    assert not auth._path_within(machine_local, copied_source.parents[1])
