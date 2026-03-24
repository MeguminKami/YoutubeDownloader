"""
Diagnostic script to test yt-dlp execution in frozen builds.
Run this from the same directory as the .exe to diagnose issues.
"""
import os
import sys
import subprocess

def main():
    print("=" * 60)
    print("YoutubeGrab Diagnostic Tool")
    print("=" * 60)

    # Check frozen state
    frozen = getattr(sys, 'frozen', False)
    print(f"\nFrozen: {frozen}")
    print(f"Executable: {sys.executable}")

    if frozen:
        meipass = getattr(sys, '_MEIPASS', None)
        print(f"_MEIPASS: {meipass}")
        exe_dir = os.path.dirname(sys.executable)
        print(f"Exe directory: {exe_dir}")

        # Check for yt-dlp in expected locations
        candidates = []
        if meipass:
            candidates.append(os.path.join(meipass, 'yt-dlp.exe'))
        candidates.append(os.path.join(exe_dir, 'yt-dlp.exe'))

        print("\nSearching for yt-dlp.exe:")
        yt_dlp_path = None
        for path in candidates:
            exists = os.path.isfile(path)
            print(f"  {path}: {'EXISTS' if exists else 'NOT FOUND'}")
            if exists and not yt_dlp_path:
                yt_dlp_path = path

        if yt_dlp_path:
            print(f"\nUsing yt-dlp at: {yt_dlp_path}")
            print(f"File size: {os.path.getsize(yt_dlp_path)} bytes")

            # Try to run yt-dlp --version
            print("\nTesting yt-dlp --version:")
            try:
                result = subprocess.run(
                    [yt_dlp_path, '--version'],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    stdin=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                )
                print(f"  Return code: {result.returncode}")
                print(f"  stdout: {result.stdout.strip()}")
                if result.stderr:
                    print(f"  stderr: {result.stderr.strip()}")
            except Exception as e:
                print(f"  ERROR: {type(e).__name__}: {e}")

            # Try to run yt-dlp --list-formats on a test URL
            test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            print(f"\nTesting yt-dlp --list-formats {test_url}:")
            try:
                result = subprocess.run(
                    [yt_dlp_path, '--list-formats', '--no-warnings', test_url],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    stdin=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                )
                print(f"  Return code: {result.returncode}")
                if result.stdout:
                    lines = result.stdout.strip().split('\n')
                    print(f"  stdout ({len(lines)} lines):")
                    for line in lines[:10]:
                        print(f"    {line}")
                    if len(lines) > 10:
                        print(f"    ... ({len(lines) - 10} more lines)")
                if result.stderr:
                    print(f"  stderr: {result.stderr.strip()[:500]}")
            except Exception as e:
                print(f"  ERROR: {type(e).__name__}: {e}")
        else:
            print("\nERROR: yt-dlp.exe not found in any expected location!")

        # Also check for ffmpeg
        print("\nSearching for ffmpeg.exe:")
        for path in [os.path.join(d, 'ffmpeg.exe') for d in [meipass, exe_dir] if d]:
            exists = os.path.isfile(path)
            print(f"  {path}: {'EXISTS' if exists else 'NOT FOUND'}")

    else:
        print("\nNot running in frozen mode. Checking PATH...")
        import shutil
        yt_dlp = shutil.which('yt-dlp')
        print(f"yt-dlp on PATH: {yt_dlp}")
        ffmpeg = shutil.which('ffmpeg')
        print(f"ffmpeg on PATH: {ffmpeg}")

    print("\n" + "=" * 60)
    input("Press Enter to exit...")

if __name__ == '__main__':
    main()
