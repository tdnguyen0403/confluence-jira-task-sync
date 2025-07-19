@echo off
REM Load environment variables from .env file
setlocal enabledelayedexpansion

REM Change this if your .env is in a different folder
set ENV_FILE=.env

if not exist %ENV_FILE% (
    echo .env file not found!
    exit /b 1
)

for /f "usebackq tokens=* delims=" %%A in (%ENV_FILE%) do (
    set "line=%%A"
    REM Ignore empty lines and comments
    if not "!line!"=="" if "!line:~0,1!" neq "#" (
        for /f "tokens=1* delims==" %%B in ("!line!") do (
            set "key=%%B"
            set "value=%%C"
            echo Setting !key! = !value!
            set "!key!=!value!"
        )
    )
)

endlocal & (
    REM Export variables to parent context
    for /f "usebackq tokens=* delims=" %%A in (%ENV_FILE%) do (
        set "line=%%A"
        if not "!line!"=="" if "!line:~0,1!" neq "#" (
            for /f "tokens=1* delims==" %%B in ("!line!") do (
                set "key=%%B"
                set "value=%%C"
                call set "!key!=!value!"
            )
        )
    )
)

echo All variables loaded.
pause >nul
