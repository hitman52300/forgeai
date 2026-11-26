@echo off
rem One-click start for ForgeAI (same launcher as ForgeAI.exe, run by the signed Python interpreter).
rem Use this on machines where Windows Smart App Control blocks unsigned .exe files.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" launcher\forgeai_launcher.py
) else (
  py -3 launcher\forgeai_launcher.py
)
