@echo off
rem Builds ForgeAI.exe (the one-click launcher) into the ForgeAI folder.
cd /d "%~dp0\.."
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe -m PyInstaller --onefile --console --name ForgeAI --distpath . --workpath data\generated\pyinstaller_build --specpath launcher launcher\forgeai_launcher.py
