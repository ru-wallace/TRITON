#!/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
BASE_DIR="$(dirname "$SCRIPT_DIR")"


if [ -f "$BASE_DIR/python_scripts/.env" ]
    then # load environment variables from .env file
    export $(grep -v '^#' "$BASE_DIR/python_scripts/.env" | xargs)
    else
    echo "Error: .env file not found"
    exit 1
fi


ROUTINE_FILE=""
SESSION_NAME=""

source "$CONDA_DIRECTORY/etc/profile.d/conda.sh"
conda activate ids_device


# Parse options
while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--console)
            python "$BASE_DIR/python_scripts/console_interface.py"
            exit 0
            ;;
        -f|--focus)
            python "$BASE_DIR/python_scripts/get_sharpness.py"
            exit 0
            ;;
        -q|--query)
            echo -n "Checking for process..."
            RUNCAM_STATUS=$(timeout 3 cat "$PIPE_OUT_FILE")
            echo -en "\e[K"
            if [ -z "${RUNCAM_STATUS}" ]; then
                echo -e "\rNo Runcam processes detected"
            else
                echo -e "\rStatus: $RUNCAM_STATUS"
            fi
            exit 0
            ;;
        -x|--stop)
            echo -n "Checking for process..."
            RUNCAM_STATUS=$(timeout 3 cat "$PIPE_OUT_FILE")
            if [ -z "${RUNCAM_STATUS}" ]; then
                echo -e "\rNo Runcam processes detected"
                exit 0
            fi
            echo -e "\rProcess found:\e[K"
            echo "$RUNCAM_STATUS"
            echo "Stopping Process..."
            echo -n "STOP" > "$PIPE_IN_FILE" &
            sleep .5
            STOP_STATUS=$(timeout 3 cat "$PIPE_OUT_FILE")
            
            echo "Stopping: $STOP_STATUS"
            if [ "$STOP_STATUS" = "STOPPING" ]; then
                echo "Process Successfully Stopped"
            else
                echo "Failed to stop process"
                exit 0
            fi

            
            
            
            exit 0
            ;;
        
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  -h, --help              Show this help message"
            echo "  -r, --routine FILE      Specify a routine file. The ./routines directory in IDS directory will be looked at if full path not specified"
            echo "  -s, --session           Specify session name"
            echo "  -f, --focus             Test Focus of camera"
            echo "  -c, --console           Open Console Interface for Camera"
            echo "  -q, --query             Check for current runcam process"
            echo "  -x, --stop              Stop current running sessions"
            exit 0
            ;;
        -r|--routine)
             if [ -n "$2" ]; then
                ROUTINE_FILE="$2"
                shift 2
            else
                echo "Error: Argument for $1 is missing" >&2
                exit 1
            fi
            ;;
        -s|--session)
             if [ -n "$2" ]; then
                SESSION_NAME="$2"
                shift 2
            else
                echo "Error: Argument for $1 is missing" >&2
                exit 1
            fi
            ;;
            
        *)
            echo "Error: Unknown option $1 - Use runcam -h or --help for commands" >&2
            exit 1
            ;;
    esac
done

if [ -z "$ROUTINE_FILE" ]; then
    echo "Error: Required argument -r/--routine is missing. Use runcam --help for help." >&2
    exit 1
fi

if [ -z "$SESSION_NAME" ]; then
    echo "Error: Required argument -s/--session is missing. Use runcam --help for help." >&2
    exit 1
fi




if [ ! -f "$ROUTINE_FILE" ]; then
    if [ ! -f "$DATA_DIRECTORY/routines/$ROUTINE_FILE" ]; then
        echo "Routine File  '$ROUTINE_FILE' Does not exist"
        exit 1
    fi
fi




#For setting up IDS Peak libraries
#export LD_LIBRARY_PATH="/opt/ids-peak-with-ueyetl_2.7.1.0-16417_arm64/lib:$LD_LIBRARY_PATH"  &> /dev/null
#export GENICAM_GENTL64_PATH="/opt/ids-peak-with-ueyetl_2.7.1.0-16417_arm64/lib/ids/cti"  &> /dev/null
#export GENICAM_GENTL32_PATH="/opt/ids-peak-with-ueyetl_2.7.1.0-16417_arm64/lib/ids/cti"  &> /dev/null


cd "$SCRIPT_DIR/.."  &> /dev/null




# Launch Python script with named arguments


python "$BASE_DIR/python_scripts/auto_capture.py" --routine "$ROUTINE_FILE" --session "$SESSION_NAME"  >/dev/null &

disown -h $!


echo "Capture started."

cd -