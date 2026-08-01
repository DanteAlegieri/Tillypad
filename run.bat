@echo off
set PYTHON_EXE=C:\Users\Dante Alegieri\AppData\Local\Programs\Python\Python313\python.exe

if not exist "%PYTHON_EXE%" (
    echo Python не найден по адресу:
    echo %PYTHON_EXE%
    pause
    exit /b 1
)

if not exist ".env" (
    echo Не найден файл .env
    echo Скопируйте .env.example в .env и вставьте токен.
    pause
    exit /b 1
)

start "" http://127.0.0.1:8000
"%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
pause
