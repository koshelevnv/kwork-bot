#!/usr/bin/env bash
# =============================================================
#  Kwork Parser Bot — установка и управление на Linux VPS
#  Поддержка: Ubuntu/Debian, CentOS/RHEL, Fedora, Alpine, Arch
#
#  Нужен VPS? https://play2go.cloud/?ref_id=TAiMBIAReXI
# =============================================================

set -euo pipefail

# ── Конфигурация ─────────────────────────────────────────────
REPO_URL="https://github.com/koshelevnv/kwork-bot.git"
BOT_DIR="$HOME/kwork-bot"
SCREEN_NAME="kwork_bot"
VENV_DIR="$BOT_DIR/.venv"
LOG_PATTERN="$BOT_DIR/logs"
PYTHON_CMD=""   # определяется автоматически

# ── Цвета ────────────────────────────────────────────────────
R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'
C='\033[0;36m'; B='\033[1m'; N='\033[0m'

# ── Утилиты ──────────────────────────────────────────────────
die()  { echo -e "${R}[ОШИБКА]${N} $*" >&2; exit 1; }
info() { echo -e "${C}[INFO]${N} $*"; }
ok()   { echo -e "${G}[OK]${N} $*"; }
warn() { echo -e "${Y}[WARN]${N} $*"; }

require_root_or_sudo() {
    if [[ $EUID -ne 0 ]] && ! command -v sudo &>/dev/null; then
        die "Требуется root или sudo для установки системных пакетов."
    fi
}

run_as_root() {
    if [[ $EUID -eq 0 ]]; then "$@"; else sudo "$@"; fi
}

# ── Определение пакетного менеджера ─────────────────────────
detect_pkg_manager() {
    if   command -v apt-get &>/dev/null; then echo "apt"
    elif command -v dnf     &>/dev/null; then echo "dnf"
    elif command -v yum     &>/dev/null; then echo "yum"
    elif command -v apk     &>/dev/null; then echo "apk"
    elif command -v pacman  &>/dev/null; then echo "pacman"
    else die "Не удалось определить пакетный менеджер."
    fi
}

# ── Установка git и screen ───────────────────────────────────
install_base_packages() {
    local pm="$1"
    info "Устанавливаю git, screen..."
    case "$pm" in
        apt)    run_as_root apt-get update -qq
                run_as_root apt-get install -y git screen ;;
        dnf)    run_as_root dnf install -y git screen ;;
        yum)    run_as_root yum install -y git screen ;;
        apk)    run_as_root apk add --no-cache git screen ;;
        pacman) run_as_root pacman -Sy --noconfirm git screen ;;
    esac
}

# ── Установка Python 3.11 ────────────────────────────────────
install_python311() {
    local pm="$1"

    # Уже есть?
    for cmd in python3.11 python3; do
        if command -v "$cmd" &>/dev/null; then
            local ver
            ver=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
            local major minor
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [[ $major -eq 3 && $minor -ge 11 ]]; then
                PYTHON_CMD="$cmd"
                ok "Python $ver уже установлен: $cmd"
                return 0
            fi
        fi
    done

    info "Устанавливаю Python 3.11..."
    case "$pm" in
        apt)
            # Ubuntu 22.04+ имеет python3.11 в universe; для 20.04 нужен deadsnakes
            if ! run_as_root apt-get install -y python3.11 python3.11-venv python3.11-dev 2>/dev/null; then
                info "Добавляю deadsnakes PPA (Ubuntu 20.04)..."
                run_as_root apt-get install -y software-properties-common
                run_as_root add-apt-repository -y ppa:deadsnakes/ppa
                run_as_root apt-get update -qq
                run_as_root apt-get install -y python3.11 python3.11-venv python3.11-dev
            fi
            ;;
        dnf)
            # Fedora 36+ / RHEL 9+
            run_as_root dnf install -y python3.11 python3.11-devel 2>/dev/null \
                || run_as_root dnf install -y python311 python311-devel
            ;;
        yum)
            # CentOS 7/8: нужен EPEL
            run_as_root yum install -y epel-release
            run_as_root yum install -y python311 python311-devel 2>/dev/null \
                || die "python3.11 не найден в репозитории. Установите вручную: https://www.python.org"
            ;;
        apk)
            # Alpine — обычно python3 ≥ 3.11 в edge/main
            run_as_root apk add --no-cache python3 py3-pip python3-dev
            ;;
        pacman)
            # Arch — rolling release, python всегда актуален
            run_as_root pacman -Sy --noconfirm python
            ;;
    esac

    # Определяем команду после установки
    for cmd in python3.11 python3; do
        if command -v "$cmd" &>/dev/null; then
            PYTHON_CMD="$cmd"
            break
        fi
    done
    [[ -n "$PYTHON_CMD" ]] || die "python3.11 установить не удалось."
    ok "Python $($PYTHON_CMD --version) готов."
}

# ── Проверить/установить pip и venv ─────────────────────────
ensure_pip_venv() {
    local pm="$1"
    local pyver
    pyver=$("$PYTHON_CMD" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")

    # На Debian/Ubuntu python3.X-venv всегда нужен для создания venv
    # (бандлированные wheel-файлы не входят в базовый пакет python3)
    if [[ "$pm" == "apt" ]]; then
        info "Устанавливаю python${pyver}-venv..."
        run_as_root apt-get install -y "python${pyver}-venv"
    elif ! "$PYTHON_CMD" -c "import ensurepip" &>/dev/null 2>&1; then
        info "Устанавливаю venv для python${pyver}..."
        case "$pm" in
            dnf|yum) run_as_root "${pm}" install -y "python${pyver}-devel" 2>/dev/null || true ;;
            apk)    run_as_root apk add --no-cache python3 ;;
            pacman) run_as_root pacman -Sy --noconfirm python ;;
        esac
    fi

    if ! "$PYTHON_CMD" -m pip --version &>/dev/null 2>&1; then
        info "Устанавливаю pip..."
        case "$pm" in
            apt)    run_as_root apt-get install -y python3-pip 2>/dev/null || true ;;
            dnf|yum) run_as_root "${pm}" install -y python3-pip 2>/dev/null || true ;;
            apk)    run_as_root apk add --no-cache py3-pip ;;
            pacman) run_as_root pacman -Sy --noconfirm python-pip ;;
        esac
        "$PYTHON_CMD" -m ensurepip --upgrade 2>/dev/null || true
    fi
}

# ── Клонировать / обновить репозиторий ───────────────────────
clone_or_update_repo() {
    if [[ "$REPO_URL" == *"YOUR_USER"* ]]; then
        echo
        echo -e "${Y}REPO_URL не настроен в скрипте.${N}"
        read -rp "Введите URL GitHub-репозитория: " REPO_URL
        [[ -n "$REPO_URL" ]] || die "URL не может быть пустым."
    fi

    if [[ -d "$BOT_DIR/.git" ]]; then
        info "Репозиторий уже скачан. Обновляю..."
        git -C "$BOT_DIR" pull --ff-only
    else
        info "Клонирую $REPO_URL → $BOT_DIR"
        git clone "$REPO_URL" "$BOT_DIR"
    fi
}

# ── Создать виртуальное окружение и установить зависимости ───
setup_venv() {
    # На Debian/Ubuntu venv требует отдельного пакета python3.X-venv
    if command -v apt-get &>/dev/null; then
        local pyver
        pyver=$("$PYTHON_CMD" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        info "Устанавливаю python${pyver}-venv..."
        run_as_root apt-get install -y "python${pyver}-venv" -qq
    fi

    if [[ ! -d "$VENV_DIR" ]]; then
        info "Создаю виртуальное окружение..."
        "$PYTHON_CMD" -m venv "$VENV_DIR"
    fi
    info "Устанавливаю/обновляю зависимости..."
    "$VENV_DIR/bin/pip" install --upgrade pip -q
    "$VENV_DIR/bin/pip" install -r "$BOT_DIR/requirements.txt" -q
    ok "Зависимости установлены."
}

# ── Интерактивная настройка .env ─────────────────────────────
configure_env() {
    local env_file="$BOT_DIR/.env"

    if [[ -f "$env_file" ]]; then
        warn ".env уже существует. Пропускаю настройку."
        return
    fi

    echo
    echo -e "${B}Настройка .env${N}"
    echo "─────────────────────────────────────────"

    while true; do
        read -rp "Telegram Bot Token (от @BotFather): " token
        [[ -n "$token" ]] && break
        warn "Токен не может быть пустым."
    done

    read -rp "Admin IDs через запятую (необязательно, Enter чтобы пропустить): " admin_ids

    {
        echo "TELEGRAM_BOT_TOKEN=$token"
        [[ -n "$admin_ids" ]] && echo "ADMIN_IDS=$admin_ids"
    } > "$env_file"

    ok ".env создан: $env_file"
}

# ── Проверить, запущен ли бот в screen ───────────────────────
is_running() {
    screen -list 2>/dev/null | grep -q "\.$SCREEN_NAME"
}

# ── Запустить бота ───────────────────────────────────────────
start_bot() {
    # Установка при первом запуске
    if [[ ! -d "$BOT_DIR" ]] || [[ ! -f "$VENV_DIR/bin/python" ]]; then
        echo
        echo -e "${B}Первый запуск — установка...${N}"
        echo "═══════════════════════════════════════════"
        require_root_or_sudo
        local pm
        pm=$(detect_pkg_manager)
        install_base_packages "$pm"
        install_python311 "$pm"
        ensure_pip_venv "$pm"
        clone_or_update_repo
        setup_venv
        configure_env
        mkdir -p "$BOT_DIR/logs"
        echo "═══════════════════════════════════════════"
        ok "Установка завершена."
    fi

    # Нет .env → нельзя запустить
    if [[ ! -f "$BOT_DIR/.env" ]]; then
        configure_env
    fi

    if is_running; then
        warn "Бот уже запущен (screen: $SCREEN_NAME)."
        return
    fi

    local log_file="$BOT_DIR/logs/bot.log"
    mkdir -p "$BOT_DIR/logs"

    info "Запускаю бота в screen-сессии '$SCREEN_NAME'..."
    screen -dmS "$SCREEN_NAME" bash -c \
        "cd '$BOT_DIR' && source '$VENV_DIR/bin/activate' && python main.py >> '$log_file' 2>&1"

    sleep 3
    if is_running; then
        ok "Бот запущен. Присоединиться: screen -r $SCREEN_NAME"
    else
        echo
        warn "Бот упал при старте. Последние строки лога:"
        echo "─────────────────────────────────────────"
        tail -n 30 "$log_file" 2>/dev/null || warn "Лог пуст."
        echo "─────────────────────────────────────────"
        die "Проверьте токен в $BOT_DIR/.env"
    fi
}

# ── Статус и логи ────────────────────────────────────────────
show_status() {
    echo
    echo -e "${B}Статус бота${N}"
    echo "─────────────────────────────────────────"

    if is_running; then
        echo -e "  Состояние : ${G}Запущен${N} (screen: $SCREEN_NAME)"
    else
        echo -e "  Состояние : ${R}Остановлен${N}"
    fi

    echo -e "  Директория: $BOT_DIR"
    echo -e "  Venv      : $VENV_DIR"

    # Последний лог-файл
    local log_file
    log_file=$(ls -t "$LOG_PATTERN"/*.log 2>/dev/null | head -1 || true)

    echo
    if [[ -f "$log_file" ]]; then
        echo -e "${B}Последние 30 строк лога: $log_file${N}"
        echo "─────────────────────────────────────────"
        tail -n 30 "$log_file"
    else
        warn "Лог-файл не найден ($LOG_PATTERN/*.log)"
        # Попробуем вывод screen
        if is_running; then
            echo -e "${B}Вывод screen (последние строки):${N}"
            echo "─────────────────────────────────────────"
            screen -S "$SCREEN_NAME" -X hardcopy /tmp/kwork_bot_screen.txt 2>/dev/null \
                && tail -n 20 /tmp/kwork_bot_screen.txt && rm -f /tmp/kwork_bot_screen.txt \
                || warn "Не удалось прочитать вывод screen."
        fi
    fi
    echo
}

# ── Остановить бота ──────────────────────────────────────────
stop_bot() {
    if ! is_running; then
        warn "Бот не запущен."
        return
    fi
    info "Останавливаю screen-сессию '$SCREEN_NAME'..."
    screen -S "$SCREEN_NAME" -X quit
    sleep 1
    if is_running; then
        warn "Сессия ещё жива. Принудительная остановка..."
        screen -S "$SCREEN_NAME" -X kill 2>/dev/null || true
    fi
    ok "Бот остановлен."
}

# ── Обновить бота ────────────────────────────────────────────
update_bot() {
    if [[ ! -d "$BOT_DIR/.git" ]]; then
        warn "Бот не установлен. Сначала запустите установку (пункт 1)."
        return
    fi

    local was_running=false
    if is_running; then
        was_running=true
        info "Останавливаю бота перед обновлением..."
        stop_bot
    fi

    info "Обновляю код из репозитория..."
    git -C "$BOT_DIR" fetch origin main || die "Не удалось получить обновления из репозитория."
    git -C "$BOT_DIR" reset --hard origin/main

    info "Обновляю зависимости..."
    "$VENV_DIR/bin/pip" install --upgrade pip -q
    "$VENV_DIR/bin/pip" install -r "$BOT_DIR/requirements.txt" -q
    ok "Зависимости обновлены."

    if "$was_running"; then
        info "Запускаю бота..."
        start_bot
    else
        ok "Обновление завершено. Бот не запущен — используйте пункт 1."
    fi
}

# ── Главное меню ─────────────────────────────────────────────
print_menu() {
    clear
    echo -e "${B}${C}"
    echo "  ╔══════════════════════════════════════╗"
    echo "  ║      Kwork Parser Bot — Управление   ║"
    echo "  ╠══════════════════════════════════════╣"

    if is_running; then
        echo -e "  ║  Статус: ${G}● Запущен${C}                    ║"
    else
        echo -e "  ║  Статус: ${R}● Остановлен${C}                 ║"
    fi

    echo "  ╠══════════════════════════════════════╣"
    echo "  ║  1. Запустить (установить если нужно)║"
    echo "  ║  2. Статус и логи                    ║"
    echo "  ║  3. Остановить бота                  ║"
    echo "  ║  4. Обновить бота                    ║"
    echo "  ║  5. Выйти                            ║"
    echo "  ╚══════════════════════════════════════╝"
    echo -e "${N}"
    echo -n "  Выберите пункт [1-5]: "
}

main() {
    # ── Первая установка — без меню ──────────────────────────────
    if [[ ! -d "$BOT_DIR/.git" ]] || [[ ! -f "$VENV_DIR/bin/python" ]]; then
        echo -e "${B}${C}"
        echo "  ╔══════════════════════════════════════╗"
        echo "  ║      Kwork Parser Bot — Установка    ║"
        echo "  ╚══════════════════════════════════════╝"
        echo -e "${N}"

        local token="" admin_ids=""
        if [[ ! -f "$BOT_DIR/.env" ]]; then
            while true; do
                read -rp "  Telegram Bot Token (от @BotFather): " token
                [[ -n "$token" ]] && break
                warn "Токен не может быть пустым."
            done
            read -rp "  Admin IDs через запятую (необязательно, Enter — пропустить): " admin_ids
        fi

        echo
        info "Начинаю установку..."
        require_root_or_sudo
        local pm
        pm=$(detect_pkg_manager)
        install_base_packages "$pm"
        install_python311 "$pm"
        ensure_pip_venv "$pm"
        clone_or_update_repo

        # Записать .env после клонирования репозитория (если ещё нет)
        local env_file="$BOT_DIR/.env"
        if [[ ! -f "$env_file" ]] && [[ -n "$token" ]]; then
            { echo "TELEGRAM_BOT_TOKEN=$token"
              [[ -n "$admin_ids" ]] && echo "ADMIN_IDS=$admin_ids"; } > "$env_file"
            ok ".env создан."
        fi

        setup_venv
        mkdir -p "$BOT_DIR/logs"
        local log_file="$BOT_DIR/logs/bot.log"

        info "Запускаю бота..."
        screen -dmS "$SCREEN_NAME" bash -c \
            "cd '$BOT_DIR' && source '$VENV_DIR/bin/activate' && python main.py >> '$log_file' 2>&1"
        sleep 3
        if is_running; then
            echo
            ok "Бот запущен!"
        else
            echo
            warn "Бот упал при старте. Последние строки лога:"
            echo "─────────────────────────────────────────"
            tail -n 30 "$log_file" 2>/dev/null || warn "Лог пуст."
            echo "─────────────────────────────────────────"
            die "Проверьте токен в $BOT_DIR/.env"
        fi

        echo
        read -rp "  Нажмите Enter для перехода в меню управления..." _
    fi

    # ── Меню для последующих запусков ────────────────────────────
    while true; do
        print_menu
        read -r choice

        case "$choice" in
            1) start_bot ;;
            2) show_status ;;
            3) stop_bot ;;
            4) update_bot ;;
            5)
                echo
                info "Выход из скрипта. Screen-сессия '$SCREEN_NAME' продолжает работать."
                echo
                exit 0
                ;;
            *)
                warn "Неверный пункт. Введите 1, 2, 3 или 5."
                ;;
        esac

        echo
        read -rp "  Нажмите Enter для возврата в меню..." _
    done
}

main
