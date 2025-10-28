#!/bin/bash

# Make sure we are running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root"
    exit 1
fi

# Check if `uv` is installed; if not, install it
if ! command -v uv &> /dev/null; then
    echo "Installing 'uv'..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

source $HOME/.local/bin/env

# Make sure that `uv` is indeed installed
if ! command -v uv &> /dev/null; then
    echo "'uv' installation failed. Please install it manually."
    exit 1
fi


# Check if the service started successfully
if ! systemctl start routersense-rpi-client &> /dev/null; then
    echo "Starting 'routersense-rpi-client' service failed. Regenerating systemctl config..."
    uv run generate_systemctl_config.py
    systemctl status routersense-rpi-client
fi

