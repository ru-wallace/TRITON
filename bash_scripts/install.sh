#!/bin/bash

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root. Exiting..."
    exit 1
fi

echo "Installing AEGIR..."

# Get script directory
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
BASE_DIR="$SCRIPT_DIR/.."
USER_HOME=$(getent passwd $SUDO_USER | cut -d: -f6)

RUNCAM_SYMBOLIC_LINK="/usr/local/bin/runcam"

# Check if runcam symbolic link exists
if [ -L "$RUNCAM_SYMBOLIC_LINK" ]; then
    rm "$RUNCAM_SYMBOLIC_LINK"
fi
echo "Creating symbolic link for runcam..."

ln -s "$SCRIPT_DIR/runcam.sh" "/usr/local/bin/runcam"

chmod 777 "$SCRIPT_DIR/runcam.sh"


echo "Checking for .env file..."
ENV_FILE="$BASE_DIR/.env"


# Exit if .env file exists
if [ -f "$ENV_FILE" ]; then
    echo ".env file already exists. Installation complete. Exiting..."
    exit 0
fi

echo "No .env file found."
echo "Creating .env file..."

# Create .env file and add text
DATA_DIR="$USER_HOME/TRITON_DATA"
read -e -p "Use default location for captured data: $DATA_DIR? [Y/n]" ACCEPT_DEFAULT_DIR 
if [ "$ACCEPT_DEFAULT_DIR" == "" ]; then
    ACCEPT_DEFAULT_DIR="y"
fi

ACCEPT_DEFAULT_DIR=$(echo "$ACCEPT_DEFAULT_DIR" | tr '[:upper:]' '[:lower:]')

if [ "$ACCEPT_DEFAULT_DIR" == "n" ]; then
    
    read -e -p "Enter the path to the data directory: " DATA_DIR
    if [ ! -d "$DATA_DIR" ]; then
        PARENT_DIR=$(dirname "$DATA_DIR")
        if [ ! -d "$PARENT_DIR" ]; then
            echo "Invalid directory. Exiting..."
            exit 1
        
        fi
    else
        DATA_DIR="$DATA_DIR/TRITON_DATA"
    fi
elif [ ! "$ACCEPT_DEFAULT_DIR" == "y" ]; then
    echo "Invalid input: \"$ACCEPT_DEFAULT_DIR\". Exiting..."
    exit 1
fi

echo "Enter location of IDS Peak installation:"
read -e -p "(e.g /opt/ids-peak-with-ueyetl_[version_num]_[architecture]):" IDS_PEAK_DIR

if [ ! -d "$IDS_PEAK_DIR" ]; then
    echo "IDS Peak installation directory does not exist. Exiting..."
    exit 1
fi

mkdir -p "$DATA_DIR"

echo "Increasing USB buffer size to 1000mb..."

echo 1000 > /sys/module/usbcore/parameters/usbfs_memory_mb
echo "DATA_DIRECTORY=\"$DATA_DIR\"" > "$ENV_FILE"
echo "IDS_PEAK_DIR=\"$IDS_PEAK_DIR\"" >> "$ENV_FILE"
echo "PIPE_IN_FILE=\"/tmp/TRITON_IN\"" >> "$ENV_FILE"
echo "PIPE_OUT_FILE=\"/tmp/TRITON_OUT\"" >> "$ENV_FILE"
chmod 6666 "$ENV_FILE"

echo "Installation complete. Exiting..."
