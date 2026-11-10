"""Native file selection shared by local resource settings."""
import os
import subprocess


def choose_file(kind):
    title, filters = {
        'key': ('SSH private key', 'Key files|*.pem;*.key;*.txt;*|All files|*'),
    }[kind]
    if os.name == 'nt':
        script = ("[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
                  "Add-Type -AssemblyName System.Windows.Forms; "
                  "$d = New-Object System.Windows.Forms.OpenFileDialog; "
                  f"$d.Title = '{title}'; $d.Filter = '{filters}'; "
                  "if ($d.ShowDialog() -eq 'OK') { [Console]::Write($d.FileName) }")
        done = subprocess.run(['powershell', '-NoProfile', '-STA', '-Command', script],
                              capture_output=True, timeout=300, creationflags=subprocess.CREATE_NO_WINDOW)
        return {'file': done.stdout.decode('utf-8', errors='replace').strip()}
    import tkinter
    from tkinter.filedialog import askopenfilename
    root = tkinter.Tk()
    root.withdraw()
    try:
        return {'file': askopenfilename(title=title, filetypes=[('All files', '*')])}
    finally:
        root.destroy()
