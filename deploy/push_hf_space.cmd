@echo off
rem Pushes the ForgeAI backend (API only) to a Hugging Face Space.
rem Usage:  deploy\push_hf_space.cmd <hf-username> <space-name>
rem Git will ask for a username (your HF username) and a password (paste your HF write token).
rem Only code is pushed: Dockerfile.api, requirements.txt, app/, prompts/. No .env, no data, no keys.
setlocal
if "%~2"=="" (
  echo Usage: deploy\push_hf_space.cmd ^<hf-username^> ^<space-name^>
  exit /b 1
)
set ROOT=%~dp0..
set STAGE=%ROOT%\data\generated\hf_space_stage
if exist "%STAGE%" rmdir /s /q "%STAGE%"
git clone https://huggingface.co/spaces/%1/%2 "%STAGE%" || exit /b 1
xcopy /e /i /q /y "%ROOT%\app" "%STAGE%\app" >nul
xcopy /e /i /q /y "%ROOT%\prompts" "%STAGE%\prompts" >nul
copy /y "%ROOT%\requirements.txt" "%STAGE%\requirements.txt" >nul
copy /y "%ROOT%\Dockerfile.api" "%STAGE%\Dockerfile" >nul
copy /y "%ROOT%\deploy\hf_space\README.md" "%STAGE%\README.md" >nul
for /d /r "%STAGE%\app" %%d in (__pycache__) do if exist "%%d" rmdir /s /q "%%d"
cd /d "%STAGE%"
git add -A
git commit -m "Deploy ForgeAI API"
git push
endlocal
