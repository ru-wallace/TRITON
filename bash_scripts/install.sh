#!/bin/bash


echo 'new size' > /sys/module/usbcore/parameters/usbfs_memory_mb
echo 1000 > /sys/module/usbcore/parameters/usbfs_memory_mb

#Get file path of the script
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
BASE_DIR="$SCRIPT_DIR/.."
# Check if .bash_aliases file exists
if [ -f ~/.bash_aliases ]; then
    # Append the alias to .bash_aliases
    echo "alias runcam='$SCRIPT_DIR/runcam.sh'" >> ~/.bash_aliases
else
    # Create .bash_aliases and add the alias
    echo "alias runcam='$SCRIPT_DIR/runcam.sh'" > ~/.bash_aliases
fi

# Check if .env file exists
if [ ! -f $BASE_DIR/python_scripts/.env ]; then
    # Create .env file and add text
    echo 'DATA_DIRECTORY="TRITON"'  > $BASE_DIR/python_scripts/.env
    echo 'LD_LIBRARY_PATH="/opt/ids-peak-with-ueyetl_2.7.1.0-16417_arm64/lib:$LD_LIBRARY_PATH"' >> "$SCRIPT_DIR/../python_scripts/.env"
    echo 'GENICAM_GENTL64_PATH="/opt/ids-peak-with-ueyetl_2.7.1.0-16417_arm64/lib/ids/cti" ' >> "$SCRIPT_DIR/../python_scripts/.env"
    echo 'GENICAM_GENTL32_PATH="/opt/ids-peak-with-ueyetl_2.7.1.0-16417_arm64/lib/ids/cti"' >> "$SCRIPT_DIR/../python_scripts/.env"
fi