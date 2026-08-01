@echo off
setlocal
set PYTHON_EXE=C:\Users\Dante Alegieri\AppData\Local\Programs\Python\Python313\python.exe

if not exist "%PYTHON_EXE%" (
    echo Python не найден:
    echo %PYTHON_EXE%
    pause
    exit /b 1
)

"%PYTHON_EXE%" -m pip install -r requirements.txt
echo.
echo Зависимости установлены.
pause
