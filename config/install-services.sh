#!/bin/bash
# Render the systemd unit templates for this machine and install them.
#
# The units can't be committed ready to use: they need the account name, the
# checkout path and the interpreter path, and none of those are fixed any more.
# Raspberry Pi OS stopped creating a default `pi` user in 2022, and the
# dashboard can be cloned anywhere.
#
# install.sh and update.sh both call this, so the unit files on disk can never
# drift apart between a fresh install and an upgrade. Runnable on its own too,
# which is the quickest way to repair the units after moving the checkout.

set -e

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUN_USER="${RUN_USER:-$(id -un)}"
PYTHON="${PYTHON:-$APP_DIR/.venv/bin/python}"

if [ ! -x "$PYTHON" ]; then
    echo "Warning: $PYTHON is not executable yet - the units will point at it anyway." >&2
    echo "         Run install.sh to create the virtualenv." >&2
fi

for unit in dashboard-backend dashboard-hardware; do
    template="$APP_DIR/config/$unit.service.in"
    if [ ! -f "$template" ]; then
        echo "Missing unit template: $template" >&2
        exit 1
    fi
    # `sudo tee` rather than `sed > file && sudo cp`, so nothing lands in a
    # world-writable temp file on the way to /etc.
    sed -e "s|@@APP_DIR@@|$APP_DIR|g" \
        -e "s|@@RUN_USER@@|$RUN_USER|g" \
        -e "s|@@PYTHON@@|$PYTHON|g" \
        "$template" | sudo tee "/etc/systemd/system/$unit.service" > /dev/null
    echo "  installed /etc/systemd/system/$unit.service"
done

sudo systemctl daemon-reload
