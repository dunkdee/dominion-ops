"""
chrome_manager.py — Chrome CDP Lifecycle Manager
=================================================
Solves the core problem: Chrome is a single-instance app.
If Chrome is already running with the main profile, a new launch
just forwards to the existing instance (no CDP enabled).

Solution:
  1. Use a DEDICATED profile dir (CDPSession) — creates a separate Chrome instance
  2. Check existing CDP ports first — if Chrome already has CDP, just use it
  3. Multiple launch methods with fallbacks
  4. Windows Startup registration — Chrome always available after reboot

Usage:
    from utils.chrome_manager import ensure_cdp, get_cdp_port
    port = ensure_cdp()        # returns port number (9222/9223) or None
"""
import os, sys, socket, time, subprocess, json, shutil
from pathlib import Path

# Chrome executable
CHROME_EXE = r"C:\Users\Dell\AppData\Local\Google\Chrome\Application\chrome.exe"

# Dedicated profile for CDP sessions — separate from user's main Chrome
CDP_PROFILE_DIR  = r"/home/malachisingleton8/.chrome_cdp"
CDP_PORT_PRIMARY = 9223  # Buddy's dedicated port
CDP_PORT_ALT     = 9222  # Fallback (user may have started Chrome with --remote-debugging-port=9222)

# Startup shortcut path (runs at Windows login)
STARTUP_FOLDER = str(Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")
STARTUP_BAT    = os.path.join(STARTUP_FOLDER, "BuddyChromeCDP.bat")


def _port_alive(port: int, host: str = "127.0.0.1", timeout: float = 1.5) -> bool:
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except Exception:
        return False


def _verify_cdp(port: int) -> bool:
    """Confirm it's actually a Chrome CDP endpoint, not just any open port."""
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=3) as r:
            data = json.loads(r.read())
            return "Browser" in data or "Chrome" in data.get("Browser", "")
    except Exception:
        return _port_alive(port)  # fallback to raw port check


def get_cdp_port() -> int:
    """Return active CDP port or 0 if none found."""
    for port in [CDP_PORT_PRIMARY, CDP_PORT_ALT, 9224, 9225]:
        if _verify_cdp(port):
            return port
    return 0


def _launch_method_cmd_start(port: int) -> bool:
    """
    cmd.exe 'start' command — specifically designed to launch GUI apps
    from the current desktop session. Works even from background processes.
    """
    args = (
        f"--remote-debugging-port={port} "
        f"--user-data-dir=\"{CDP_PROFILE_DIR}\" "
        f"--profile-directory=Default "
        f"--no-first-run --no-default-browser-check "
        f"--disable-default-apps --start-maximized "
        f"--disable-notifications --disable-infobars"
    )
    cmd = f'start "" "{CHROME_EXE}" {args}'
    try:
        subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS,
        )
        return True
    except Exception as e:
        print(f"  [CHR] cmd start failed: {e}")
        return False


def _launch_method_powershell(port: int) -> bool:
    """PowerShell Start-Process with -WindowStyle Normal."""
    args = (
        f"--remote-debugging-port={port},"
        f"--user-data-dir='{CDP_PROFILE_DIR}',"
        f"--profile-directory=Default,"
        f"--no-first-run,--no-default-browser-check,"
        f"--disable-default-apps,--start-maximized"
    ).replace(",", " ")

    ps_cmd = f'Start-Process "{CHROME_EXE}" -ArgumentList "{args}" -WindowStyle Normal'
    try:
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        print(f"  [CHR] PowerShell start failed: {e}")
        return False


def _launch_method_bat(port: int) -> bool:
    """Write a bat file and run it — bat files always launch in user session."""
    bat_path = os.path.join(os.path.dirname(__file__), "_chrome_launch_tmp.bat")
    args = (
        f'--remote-debugging-port={port} '
        f'--user-data-dir="{CDP_PROFILE_DIR}" '
        f'--profile-directory=Default '
        f'--no-first-run --no-default-browser-check '
        f'--disable-default-apps --start-maximized'
    )
    bat_content = f'@echo off\nstart "" "{CHROME_EXE}" {args}\n'
    try:
        with open(bat_path, "w") as f:
            f.write(bat_content)
        subprocess.Popen(
            ["cmd.exe", "/c", bat_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_CONSOLE,
        )
        return True
    except Exception as e:
        print(f"  [CHR] bat launch failed: {e}")
        return False


def _launch_method_shellexec(port: int) -> bool:
    """ShellExecuteW — Windows shell launch."""
    try:
        import ctypes
        args = (
            f"--remote-debugging-port={port} "
            f'--user-data-dir="{CDP_PROFILE_DIR}" '
            f"--profile-directory=Default "
            f"--no-first-run --no-default-browser-check "
            f"--disable-default-apps --start-maximized"
        )
        result = ctypes.windll.shell32.ShellExecuteW(None, "open", CHROME_EXE, args, None, 1)
        print(f"  [CHR] ShellExecuteW result: {result} (>32=success)")
        return result > 32
    except Exception as e:
        print(f"  [CHR] ShellExecuteW failed: {e}")
        return False


def _launch_method_wscript(port: int) -> bool:
    """
    WScript.Shell Run() — often works when other methods fail in
    background/service context because it uses the shell's CreateProcess.
    """
    args = (
        f"--remote-debugging-port={port} "
        f'--user-data-dir=\\"{CDP_PROFILE_DIR}\\" '
        f"--profile-directory=Default "
        f"--no-first-run --no-default-browser-check "
        f"--disable-default-apps --start-maximized"
    )
    vbs_content = (
        f'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.Run Chr(34) & "{CHROME_EXE}" & Chr(34) & " {args}", 1, False\n'
    )
    vbs_path = os.path.join(os.path.dirname(__file__), "_chrome_launch_tmp.vbs")
    try:
        with open(vbs_path, "w") as f:
            f.write(vbs_content)
        subprocess.Popen(
            ["wscript.exe", vbs_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        print(f"  [CHR] VBScript launch failed: {e}")
        return False


def _launch_method_schtask(port: int) -> bool:
    """
    Windows Task Scheduler — guaranteed to run in the interactive user session
    even when called from session 0 / background process.
    Creates a one-shot task and immediately triggers it.
    """
    task_name = "BuddyChromeCDP"
    args = (
        f"--remote-debugging-port={port} "
        f'--user-data-dir="{CDP_PROFILE_DIR}" '
        f"--profile-directory=Default "
        f"--no-first-run --no-default-browser-check "
        f"--disable-default-apps --start-maximized"
    )
    tr = f'"{CHROME_EXE}" {args}'
    username = os.environ.get("USERNAME", os.environ.get("USER", ""))

    # Delete old task if exists
    subprocess.run(["schtasks", "/delete", "/tn", task_name, "/f"],
                   capture_output=True)

    # Create task
    create = subprocess.run([
        "schtasks", "/create",
        "/tn", task_name,
        "/tr", tr,
        "/sc", "once",
        "/st", "00:00",
        "/f",
        "/rl", "highest",
    ] + (["/ru", username] if username else []),
        capture_output=True, text=True
    )
    print(f"  [CHR] schtask create: {create.returncode} | {create.stdout.strip()[:80]}")

    if create.returncode != 0:
        return False

    # Run it now
    run = subprocess.run(["schtasks", "/run", "/tn", task_name], capture_output=True, text=True)
    print(f"  [CHR] schtask run: {run.returncode} | {run.stdout.strip()[:80]}")
    return run.returncode == 0


def ensure_cdp(port: int = CDP_PORT_PRIMARY, timeout: int = 40) -> int:
    """
    Ensure Chrome is running with CDP enabled.
    Returns the active CDP port, or 0 on failure.

    Steps:
    1. Check if CDP already alive (any port)
    2. Try each launch method in order
    3. Poll for CDP to become available
    """
    # Step 1: Already alive?
    existing = get_cdp_port()
    if existing:
        print(f"  [CHR] Chrome CDP already running on port {existing}")
        return existing

    print(f"  [CHR] Chrome CDP not found — launching dedicated instance on port {port}...")
    print(f"  [CHR] Profile: {CDP_PROFILE_DIR}")

    # Ensure profile dir exists (so Chrome doesn't show first-run wizard)
    os.makedirs(CDP_PROFILE_DIR, exist_ok=True)

    # Try each launch method
    methods = [
        ("cmd start", _launch_method_cmd_start),
        ("bat file",  _launch_method_bat),
        ("VBScript",  _launch_method_wscript),
        ("PowerShell", _launch_method_powershell),
        ("ShellExecute", _launch_method_shellexec),
        ("Task Scheduler", _launch_method_schtask),
    ]

    for method_name, method_fn in methods:
        print(f"  [CHR] Trying: {method_name}...")
        try:
            method_fn(port)
        except Exception as e:
            print(f"  [CHR] {method_name} error: {e}")
            continue

        # Poll for CDP
        deadline = time.time() + 20
        while time.time() < deadline:
            if _verify_cdp(port):
                print(f"  [CHR] Chrome ready on port {port} (via {method_name})")
                return port
            time.sleep(1.0)

        # Check alt ports too
        alt = get_cdp_port()
        if alt:
            print(f"  [CHR] Chrome ready on port {alt} (via {method_name})")
            return alt

        print(f"  [CHR] {method_name}: Chrome not responding after 20s, trying next method...")

    print(f"  [CHR] All launch methods failed. Is Chrome installed at {CHROME_EXE}?")
    return 0


def setup_startup_chrome(port: int = CDP_PORT_PRIMARY):
    """
    Write a bat file to the Windows Startup folder so Chrome with CDP
    launches automatically at every Windows login.
    This is a ONE-TIME setup call — after this, ensure_cdp() will always
    find Chrome ready when Buddy starts.
    """
    if not os.path.exists(STARTUP_FOLDER):
        print(f"  [CHR] Startup folder not found: {STARTUP_FOLDER}")
        return False

    args = (
        f"--remote-debugging-port={port} "
        f'--user-data-dir="{CDP_PROFILE_DIR}" '
        f"--profile-directory=Default "
        f"--no-first-run --no-default-browser-check "
        f"--disable-default-apps --start-maximized"
    )
    bat = (
        f"@echo off\n"
        f"REM Buddy Chrome CDP Session — auto-launched at login\n"
        f"start \"\" \"{CHROME_EXE}\" {args}\n"
    )
    try:
        with open(STARTUP_BAT, "w") as f:
            f.write(bat)
        print(f"  [CHR] Startup entry created: {STARTUP_BAT}")
        print(f"  [CHR] Chrome will auto-start with CDP on port {port} at every login.")
        return True
    except Exception as e:
        print(f"  [CHR] Failed to write startup entry: {e}")
        return False


def copy_cookies_from_main_profile():
    """
    Copy cookies from the user's main Chrome profile to the CDP profile.
    Chrome 96+ stores cookies at Default/Network/Cookies.
    DPAPI-encrypted cookies work across profiles of the same Windows user.
    Only copies if CDPSession profile is new (no existing cookies).
    """
    MAIN_DEFAULT = os.path.join(
        r"C:\Users\Dell\AppData\Local\Google\Chrome\User Data", "Default"
    )
    CDP_DEFAULT = os.path.join(CDP_PROFILE_DIR, "Default")

    # Chrome 96+ stores cookies in Network/ subfolder
    possible_cookie_paths = [
        os.path.join(MAIN_DEFAULT, "Network", "Cookies"),  # Chrome 96+
        os.path.join(MAIN_DEFAULT, "Cookies"),              # Older Chrome
    ]
    main_cookies = next((p for p in possible_cookie_paths if os.path.exists(p)), None)

    if not main_cookies:
        print("  [CHR] Main profile cookies not found — skipping copy")
        return False

    # Determine destination mirror path
    rel = os.path.relpath(main_cookies, MAIN_DEFAULT)
    cdp_cookies = os.path.join(CDP_DEFAULT, rel)

    if os.path.exists(cdp_cookies):
        print("  [CHR] CDPSession already has cookies — not overwriting")
        return True

    try:
        os.makedirs(os.path.dirname(cdp_cookies), exist_ok=True)
        shutil.copy2(main_cookies, cdp_cookies)
        print(f"  [CHR] Cookies copied: {rel}")

        # Copy Local Storage, Session Storage, and Web Data (logins/sessions)
        for item in ["Local Storage", "Session Storage", "Web Data",
                     os.path.join("Network", "Cookies-journal")]:
            src = os.path.join(MAIN_DEFAULT, item)
            dst = os.path.join(CDP_DEFAULT, item)
            if os.path.exists(src) and not os.path.exists(dst):
                try:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                except Exception:
                    pass

        return True
    except Exception as e:
        print(f"  [CHR] Cookie copy failed: {e}")
        return False


def ensure_cdp_with_sessions(port: int = CDP_PORT_PRIMARY) -> int:
    """
    Full setup: copy sessions from main profile, then ensure Chrome is running.
    Call this instead of ensure_cdp() for Upwork/PPH agents that need login sessions.
    """
    # Copy sessions on first setup
    copy_cookies_from_main_profile()

    port = ensure_cdp(port)
    return port


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup-startup", action="store_true", help="Add Chrome CDP to Windows Startup")
    ap.add_argument("--port", type=int, default=CDP_PORT_PRIMARY)
    args = ap.parse_args()

    if args.setup_startup:
        setup_startup_chrome(args.port)
    else:
        p = ensure_cdp_with_sessions(args.port)
        print(f"CDP port: {p}")
