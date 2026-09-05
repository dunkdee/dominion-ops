from __future__ import annotations

from buddy_core.core import authorization as auth


def _copied_source(root):
    source = root / "buddy_core" / "core" / "authorization.py"
    source.parent.mkdir(parents=True)
    source.write_text("# copied runtime\n", encoding="utf-8")
    return source


def test_copied_buddy_home_with_repo_like_markers_is_not_a_checkout(tmp_path):
    """Regression for Foundation VM run 33962057972.

    HOME may contain all of these names while the actual Git checkout lives in
    a sibling ``~/dominion-ops`` directory. Directory names must not turn HOME
    into a repository boundary.
    """
    home = tmp_path / "home"
    source = _copied_source(home)
    for marker in (".github", "governance", "tests"):
        (home / marker).mkdir()

    assert auth._detect_checkout_root(source) is None


def test_real_git_checkout_is_detected(tmp_path):
    checkout = tmp_path / "dominion-ops"
    source = _copied_source(checkout)
    (checkout / ".git").mkdir()

    assert auth._detect_checkout_root(source) == checkout.resolve()


def test_machine_local_key_stays_outside_copied_source(tmp_path):
    home = tmp_path / "home"
    source = _copied_source(home)
    for marker in (".github", "governance", "tests"):
        (home / marker).mkdir()

    checkout = auth._detect_checkout_root(source)
    machine_local = home / ".dominion" / "authorization" / "ledger_hmac.key"

    assert checkout is None
    assert not auth._path_within(machine_local, source.parents[1])


def test_source_tree_key_is_still_rejected_by_source_boundary(tmp_path):
    home = tmp_path / "home"
    source = _copied_source(home)
    source_root = source.parents[1]
    bad_key = source_root / "config" / "ledger_hmac.key"

    assert auth._path_within(bad_key, source_root)
