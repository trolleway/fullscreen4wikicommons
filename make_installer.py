import os
import shutil
import subprocess
import sys

# Define the path to the Python script
script_path = "main.py"

# Define the output directory for the build
output_dir = "dist"


# Ensure the output directory exists
os.makedirs(output_dir, exist_ok=True)

# Run pyinstaller with the necessary options
subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        "Full Screen Viewer for Wikimedia Commons",
        "--onefile",
        "--noconsole",
        "--distpath",
        output_dir,
        script_path,
    ]
)
