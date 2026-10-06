#!/usr/bin/env sh
# Launches luniiStory, setting everything up on first run.
#
#   ./run.sh            graphical interface
#   ./run.sh list       any command line argument is passed through
set -e

cd "$(dirname "$0")"

PYTHON=${PYTHON:-python3}
VENV=.venv

if [ ! -f vendor/Lunii.QT/pkg/api/device_lunii.py ]; then
    echo "Fetching the Lunii.QT submodule..."
    git submodule update --init --recursive
fi

if [ ! -d "$VENV" ]; then
    echo "Creating the virtual environment..."
    "$PYTHON" -m venv "$VENV"
fi

# Reinstall only when the requirements are newer than the last successful run.
STAMP="$VENV/.requirements-stamp"
if [ ! -f "$STAMP" ] || [ requirements.txt -nt "$STAMP" ]; then
    echo "Installing dependencies..."
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet -r requirements.txt
    touch "$STAMP"
fi

exec "$VENV/bin/python" -m luniistory "$@"
