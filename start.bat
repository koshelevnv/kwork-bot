@echo off
chcp 65001 > nul
setlocal

set "PYTHON=py -3.11"
set "VENV_DIR=%~dp0.venv"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

echo ==========================================
echo  Kwork Parser Bot
echo ==========================================
echo.

%PYTHON% --version 2>&1
if errorlevel 1 (
    echo [!] Python 3.11 не найден.
    echo     Скачай с https://python.org и установи с галочкой "Add to PATH".
    pause
    exit /b 1
)
echo.

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [*] Создаём виртуальное окружение...
    %PYTHON% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [!] Ошибка создания виртуального окружения.
        pause
        exit /b 1
    )
    echo [+] Виртуальное окружение создано.
    echo.
)

echo [*] Активация виртуального окружения...
call "%VENV_DIR%\Scripts\activate.bat"
echo [+] Активно: %VIRTUAL_ENV%
echo.

if not exist "%~dp0.env" (
    echo [!] Файл .env не найден^^!
    echo     Скопируй .env.example -^> .env и заполни настройки.
    echo.
    pause
    exit /b 1
)

echo [*] Установка зависимостей...
echo ------------------------------------------
pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo ------------------------------------------
    echo [!] Ошибка установки зависимостей.
    pause
    exit /b 1
)
echo ------------------------------------------
echo [+] Зависимости установлены.
echo.

if not exist "%~dp0logs" mkdir "%~dp0logs"

echo [*] Запуск бота... (Ctrl+C для остановки)
echo ==========================================
echo.
python "%~dp0main.py"

echo.
echo [*] Бот остановлен.
pause
