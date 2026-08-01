@echo off
set PYTHON_EXE=C:\Users\Dante Alegieri\AppData\Local\Programs\Python\Python313\python.exe

if not exist "%PYTHON_EXE%" (
    echo Python не найден по адресу:
    echo %PYTHON_EXE%
    pause
    exit /b 1
)

"%PYTHON_EXE%" -m pip install -r requirements.txt
echo.
echo Установка завершена.
pause
