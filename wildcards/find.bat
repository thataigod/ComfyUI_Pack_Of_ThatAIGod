@echo off
setlocal enabledelayedexpansion

if "%1"=="" (
    echo Usage: find.bat ^<searchWord^>
    echo Example: find.bat red
    pause
    exit /b
)

set "searchWord=%~1"
set "searchFolder=%~dp0autowildcards"

echo Searching for "%searchWord%" in "%searchFolder%"...
echo.

:: Use quotes properly to handle spaces in paths
for /R "%searchFolder%" %%f in (*) do (
    findstr /I /C:"%searchWord%" "%%f" >nul 2>&1
    if !errorlevel! neq 1 (
        echo ========================================
        echo File: "%%f"
        echo ----------------------------------------
        findstr /N /I /C:"%searchWord%" "%%f"
        echo.
    )
)

echo Search complete.
pause
