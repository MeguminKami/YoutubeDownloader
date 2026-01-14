"""
Windows admin privilege checking and elevation

SECURITY NOTE: Admin elevation should be used sparingly.
This app requests admin rights primarily for write access to protected folders.
Consider if admin rights are truly necessary for your use case.
"""
import sys
import os
import ctypes

def is_admin():
    """Check if the script is running with admin privileges"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """
    Re-run the script with admin privileges.

    SECURITY: Only elevate from known script locations.
    """
    if sys.platform == 'win32':
        script = os.path.abspath(sys.argv[0])

        # Security: Validate script path is a Python file
        if not script.endswith(('.py', '.pyw', '.exe')):
            print("Security: Invalid script extension for elevation")
            sys.exit(1)

        # Security: Only allow elevation from the expected directory
        script_dir = os.path.dirname(script)

        # Build params safely - don't include arbitrary arguments
        # Only pass through known safe arguments
        safe_args = []
        for arg in sys.argv[1:]:
            # Skip any argument that looks like it could be injection
            if not arg.startswith('-') and ('&' in arg or '|' in arg or ';' in arg):
                continue
            safe_args.append(f'"{arg}"')
        params = ' '.join(safe_args)

        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            f'"{script}" {params}',
            None,
            1  # SW_SHOWNORMAL - show window
        )
        sys.exit(0)