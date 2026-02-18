#!/bin/bash
# RSSTools - Start script with automatic virtual environment activation

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Virtual environment directory
VENV_DIR="${SCRIPT_DIR}/venv"

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment not found at $VENV_DIR"
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    
    echo "Installing dependencies..."
    source "$VENV_DIR/bin/activate"
    pip install -r "${SCRIPT_DIR}/requirements.txt"
    echo "Virtual environment setup complete!"
else
    echo "Virtual environment found at $VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Run rsstools with provided arguments
python -m rsstools.rsstools "$@"
