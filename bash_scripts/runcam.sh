#!/bin/bash


USB_BUFFER_SIZE=$(cat /sys/module/usbcore/parameters/usbfs_memory_mb)


SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
BASE_DIR="$(dirname "$SCRIPT_DIR")"

ENV_FILE="$BASE_DIR/.env"

if [ -f "$ENV_FILE" ]
    then # load environment variables from .env file
    export $(grep -v '^#' "$ENV_FILE" | xargs)
    else
    echo "Error: .env file not found - use $SCRIPT_DIR/install.sh to create one"
    exit 1
fi

export LD_LIBRARY_PATH="$IDS_PEAK_DIR/lib:$LD_LIBRARY_PATH"
export GENICAM_GENTL64_PATH="$IDS_PEAK_DIR/lib/ids/cti" 
export GENICAM_GENTL32_PATH="$GENICAM_GENTL64_PATH"
export PATH="$IDS_PEAK_DIR/bin:$PATH"

ROUTINE_FILE=""
SESSION_NAME=""

source "$CONDA_DIRECTORY/etc/profile.d/conda.sh"
conda activate ids_device


# Parse options
while [[ $# -gt 0 ]]; do
    case "$1" in
        -b|--buffer)
            if [ "$EUID" -eq 0 ]; then
                echo "Increasing USB buffer size to 1000mb..."
                echo 1000 > /sys/module/usbcore/parameters/usbfs_memory_mb
            else
                echo "Error: Must be root to increase USB buffer size"
                echo "Exiting..."
                exit 1
            fi
            ;;
        -c|--console)
            python "$BASE_DIR/python_scripts/console_interface.py"
            exit 0
            ;;
        -f|--focus)
            python "$BASE_DIR/python_scripts/get_sharpness.py"
            exit 0
            ;;
        
        -n|--node)
            if [ -n "$2" ]; then
                NODE="$2"
                shift 2
            else
                echo "Error: Argument for $1 is missing" >&2
                exit 1
            fi
            ;;

        --get)
            if [ -n "$NODE" ]; then
                echo "$(ids_devicecommand -n $NODE --get)"
                exit 0
            else
                echo "Error: No Node Name. Use 'runcam --node [node name] --get | --set [value]"
                exit 1
            fi
            ;;
        --set)
            if [ -n "$NODE" ]; then
                if [ -n "$2" ]; then
                    NODE="$2"
                    shift 2
                else
                    echo "Error: Argument for $1 is missing" >&2
                    exit 1
            fi
                echo "$(ids_devicecommand -n $NODE --set $VALUE)"
                exit 0
            else
                echo "Error: No Node Name. Use 'runcam --node [node name] --get | --set [value]'"
                exit 1
            fi
            ;;

        -q|--query)
            echo -n "Checking for process..."
            if [ -p "$PIPE_OUT_FILE" ]; then
                RUNCAM_STATUS=$(timeout 3 cat "$PIPE_OUT_FILE")
                echo -en "\e[K"
                if [ -z "${RUNCAM_STATUS}" ]; then
                    echo -e "\rNo Runcam processes detected"
                else
                    echo -e "\rStatus: $RUNCAM_STATUS"
                fi
            else
                echo -e "\rNo Runcam processes detected"
            fi
            exit 0
            ;;
        
            -l|--log)
            echo -n "Checking for process..."
            if [ -p "$PIPE_OUT_FILE" ]; then
                RUNCAM_STATUS=$(timeout 3 cat "$PIPE_OUT_FILE")
                echo -en "\e[K"
                if [ -z "${RUNCAM_STATUS}" ]; then
                    echo -e "\rNo Runcam processes detected"
                else
                    echo -e "\rStatus: $RUNCAM_STATUS"
                    RUNCAM_SESSION_LINE=$(grep "^Session: " <<< "$RUNCAM_STATUS")
                    RUNCAM_SESSION="${RUNCAM_SESSION_LINE#Session: }" 
                    echo -e "Session: $RUNCAM_SESSION"
                    tail -f "$DATA_DIRECTORY/sessions/$RUNCAM_SESSION/output.log"
                fi
            else
                echo -e "\rNo Runcam processes detected"
            fi
            exit 0
            ;;
        -x|--stop)
            echo -n "Checking for process..."
            if ! [ -p "$PIPE_OUT_FILE" ]; then
                echo -e "\rNo Runcam processes detected"
                exit 0
            fi
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
            echo "  -r, --routine FILE      Specify a routine file. The ./routines directory in the Aegir DATA_DIRECTORY  (specified in .env) will be looked at if full path not specified"
            echo "  -s, --session           Specify session name"
            echo "  -f, --focus             Test Focus of camera"
            echo "  -c, --console           Open Console Interface for Camera"
            echo "  -q, --query             Check for active runcam process"
            echo "  -l, --log               View output log of a current active process"
            echo "  -n [ --node ] arg       Select node by name (e.g. -n "DeviceModelName")."
            echo "      --get                   Get node value and print it (e.g. -n "ExposureTime" --get)."
            echo "      --set arg               Set node value (e.g. -n "ExposureTime" --set "14000")."
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
        --run)
            if [ -n "$2" ]; then
                PYTHON_SCRIPT="$2"
                shift 2

                python "$PYTHON_SCRIPT" "$@"
                exit 0
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

#Exit if node command has run
if [ -n "$NODE" ]; then
    exit 0
fi



if [ -z "$ROUTINE_FILE" ]; then
    echo "Error: Required argument -r/--routine is missing. Use runcam --help for help." >&2
    exit 1
fi

if [ -z "$SESSION_NAME" ]; then
    echo "Error: Required argument -s/--session is missing. Use runcam --help for help." >&2
    exit 1
fi

if [ "$USB_BUFFER_SIZE" -lt 1000 ]; then
        echo "Warning: USB buffer size is less than 1000mb. Please run 'runcam -b' as root to increase the buffer size."
fi


echo -n "Checking for already running process..."
if [ -p "$PIPE_OUT_FILE" ]; then
    RUNCAM_STATUS=$(timeout 3 cat "$PIPE_OUT_FILE")
    echo -en "\e[K"
    if [ -z "${RUNCAM_STATUS}" ]; then
        echo -e "\rNo Runcam processes detected            "
    else
        echo -e "\rRuncam process already running:         "
        echo "$RUNCAM_STATUS"
        echo "Use 'runcam -x' to stop a currently running process"
        echo "Exiting..."
        exit 1
    fi
else
    echo -e "\rNo Runcam processes detected            "
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

cd - >/dev/null