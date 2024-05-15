#!/bin/bash




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
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  -h, --help              Show this help message"
            echo "  -b, --buffer [size]     Change the USB buffer size for this Linux device to [size]mb. If no size is specified, the buffer size will be set to 1000mb"
            echo "  -f, --focus             Test Focus of camera"
            echo "  -l, --log               View output log of a current active process"
            echo "  -n [ --node ] < --get | --set <value> > Get or set value of node by name (e.g. -n "ExposureTime" --set 1000)."              
            echo "  -q, --query             Check for active runcam process"
            echo "  -r, --routine FILE      Specify a routine file. The ./routines directory in the Aegir DATA_DIRECTORY  (specified in .env) will be looked at if full path not specified"
            echo "  -s, --session           Specify session name"
            echo "  -x, --stop              Send stop signal to a currently running process"
            echo "  --harvesters            Run autocam in harvesters mode"
            echo "  --run <python script file location>   ONLY USE IF YOU KNOW WHAT YOU ARE DOING: Run a python script with the environment set up as used by this tool. I.e GenTL Producer path is set.            "

            exit 0
            ;;
        -b|--buffer)
            if [ -n "$2" ]; then
                USB_BUFFER_SIZE="$2"
                shift 2
            else
                USB_BUFFER_SIZE=1000
                shift
            fi
            if [ "$EUID" -eq 0 ]; then
                if [[ "$USB_BUFFER_SIZE" =~ ^[0-9]+$ && "$USB_BUFFER_SIZE" -lt 10000 ]]; then
                    echo "Increasing USB buffer size to 1000mb..."
                    echo "$USB_BUFFER_SIZE" > /sys/module/usbcore/parameters/usbfs_memory_mb
                else
                    echo "Error: Invalid buffer size. Buffer size must be an integer below 10000." >&2
                    exit 1
                fi



            else
                echo "Error: Must be root to increase USB buffer size"
                echo "Exiting..."
                exit 1
            fi
            ;;
        -f|--focus)
            python "$BASE_DIR/python_scripts/get_sharpness.py"
            exit 0
            ;;
        --harvesters)
            HARVESTERS_MODE=1
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
        -r|--routine)
             if [ -n "$2" ]; then
                ROUTINE_FILE="$2"
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
        -s|--session)
             if [ -n "$2" ]; then
                SESSION_NAME="$2"
                shift 2
            else
                echo "Error: Argument for $1 is missing" >&2
                exit 1
            fi
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
        echo "Warning: USB buffer size is less than 1000mb. This is likely to cause errors during camera use."
        echo "Please run 'runcam -b' as root to increase the buffer size."
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

if [ -n "$HARVESTERS_MODE" ]; then
    PYTHON_SCRIPT="$BASE_DIR/python_scripts/auto_capture_harvesters.py"
else
    PYTHON_SCRIPT="$BASE_DIR/python_scripts/auto_capture.py"
fi

python "$PYTHON_SCRIPT" --routine "$ROUTINE_FILE" --session "$SESSION_NAME"  >/dev/null &

disown -h $!


echo "Capture started."

cd - >/dev/null