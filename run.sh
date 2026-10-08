#!/usr/bin/env sh
# Хронос: обёртка запуска для Linux/macOS (VPS, Railway, Render).
#
#   ./run.sh              — запустить бота
#   ./run.sh doctor       — самопроверка
#   ./run.sh migrate      — применить миграции
#   ./run.sh test         — прогнать тесты
#
# Python: .venv/bin/python, если есть, иначе python3.

set -e
root=$(cd "$(dirname "$0")" && pwd)
cd "$root"

if [ -x "$root/.venv/bin/python" ]; then
    python="$root/.venv/bin/python"
else
    python="python3"
fi

PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" export PYTHONPATH
PYTHONIOENCODING=utf-8 export PYTHONIOENCODING

command=${1:-run}
[ $# -gt 0 ] && shift

case "$command" in
    run)             exec "$python" -m chronos "$@" ;;
    doctor|check)    exec "$python" -m chronos doctor "$@" ;;
    migrate)         exec "$python" -m alembic upgrade head "$@" ;;
    migrate-history) exec "$python" -m alembic history --verbose "$@" ;;
    test)            exec "$python" -m pytest -p no:cacheprovider "$@" ;;
    *)               exec "$python" -m chronos "$command" "$@" ;;
esac
