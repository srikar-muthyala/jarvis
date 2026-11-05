import os
import sys
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
PYTHONW = HERE / ".venv" / "Scripts" / "pythonw.exe"
if not PYTHONW.exists():
    PYTHONW = HERE / ".venv" / "pythonw.exe"
WIDGET_SCRIPT = HERE / "widget.py"
ICON_PATH = HERE / "jarvis.ico"

STARTUP_DIR = Path(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"))
DESKTOP_DIR = Path(os.path.expandvars(r"%USERPROFILE%\Desktop"))

STARTUP_LNK = STARTUP_DIR / "Jarvis.lnk"
DESKTOP_LNK = DESKTOP_DIR / "Jarvis.lnk"


def create_shortcut(lnk_path: Path, description: str = "Jarvis AI Assistant") -> bool:
    """Create a Windows .lnk shortcut using PowerShell COM object."""
    ps_cmd = f"""
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut('{str(lnk_path)}')
    $Shortcut.TargetPath = '{str(PYTHONW)}'
    $Shortcut.Arguments = '"{str(WIDGET_SCRIPT)}"'
    $Shortcut.WorkingDirectory = '{str(HERE)}'
    $Shortcut.IconLocation = '{str(ICON_PATH)},0'
    $Shortcut.Description = '{description}'
    $Shortcut.WindowStyle = 1
    $Shortcut.Save()
    """
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
        return lnk_path.exists()
    except Exception as e:
        print(f"Error creating shortcut {lnk_path}: {e}")
        return False


def enable_autostart() -> bool:
    """Enable Jarvis to boot automatically with Windows."""
    success = create_shortcut(STARTUP_LNK, "Jarvis AI Auto-Start on Boot")
    # Also create desktop shortcut if not already present
    create_shortcut(DESKTOP_LNK, "Jarvis AI Assistant")
    return success


def disable_autostart() -> bool:
    """Disable Jarvis from booting automatically with Windows."""
    try:
        if STARTUP_LNK.exists():
            STARTUP_LNK.unlink()
        return True
    except Exception as e:
        print(f"Error removing startup shortcut: {e}")
        return False


def is_autostart_enabled() -> bool:
    """Check if Jarvis is currently configured to boot on Windows startup."""
    return STARTUP_LNK.exists()


def main():
    action = sys.argv[1].lower() if len(sys.argv) > 1 else "--enable"
    if action in ("--enable", "enable", "-e"):
        if enable_autostart():
            print("SUCCESS: Auto-boot enabled! Jarvis will now start automatically when Windows boots.")
            print(f"  Startup shortcut: {STARTUP_LNK}")
            print(f"  Desktop shortcut: {DESKTOP_LNK}")
        else:
            print("FAILED: Could not enable auto-boot.")
    elif action in ("--disable", "disable", "-d"):
        if disable_autostart():
            print("SUCCESS: Auto-boot disabled. Jarvis will no longer start automatically.")
        else:
            print("FAILED: Could not disable auto-boot.")
    elif action in ("--status", "status", "-s"):
        status = "ENABLED" if is_autostart_enabled() else "DISABLED"
        print(f"Jarvis Auto-Boot Status: {status}")
    else:
        print("Usage: python setup_autostart.py [--enable | --disable | --status]")


if __name__ == "__main__":
    main()
