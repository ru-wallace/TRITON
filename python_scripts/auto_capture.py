import argparse
from pathlib import Path
import json
import os
from dotenv import load_dotenv
import traceback
import sys
from datetime import datetime, timedelta
from time import time, sleep
from contextlib import contextmanager

import ms5837

import routine
import session
import ids_interface
from cam_image import Cam_Image

load_dotenv()

DATA_DIR = Path(os.environ.get("DATA_DIRECTORY"))
PIPE_IN_FILE = Path(os.environ.get("PIPE_IN_FILE"))
PIPE_OUT_FILE = Path(os.environ.get("PIPE_OUT_FILE"))

def main():
    
    """Loads a session and routine from arguments passed when calling the script.
    Call from command line with:
    $> auto_capture.py --routine [routine name] --session [session name]
    
    The order of arguments is not important.
    
    The script opens or creates a session with the name in the --session arg.
    If it can find a routine with the name in the --routine arg it will run that, 
    otherwise it will exit with error code 1.
    
    """    
    stored_strings = ""
    
    current_session: session.Session = None
    current_routine: routine.Routine = None
    def print_and_log(*args, **kwargs):
        """Function for logging output of this script. If this is run from a systemd service the output should go to the RPi logs 
        to be read with journalctl, but this also writes to a file in the session which is loaded. If there is no session loaded 
        it saves the output until one is opened and then writes it.
        """
        try:
                
            str_args = ""
            for arg in args:
                str_args+=str(arg)
            string = datetime.now().strftime("%Y/%m/%d %H:%M:%S: ") + str_args
            nonlocal stored_strings
            print(*args, **kwargs)
            if current_session is not None:
                if stored_strings != "":
                    current_session.output(stored_strings)
                    stored_strings = ""
                    
                current_session.output(string)
                
            else:
                stored_strings += string + "\n"
            
        except Exception as e: 
            traceback.print_exc(e)
    def log_error():
        with open("error_log.log", "a") as err_file:
            err_file.write(stored_strings)
    run_number = 0
    
    print_and_log("Running run_process.py")
    #Argparse is a library used for parsing arguments passed to the script when it is called from the command line
    parser = argparse.ArgumentParser(description='Get session and routine arguments')

    # Set up the named arguments
    parser.add_argument('--routine', help='Routine', required=True)
    parser.add_argument('--session', help='Session', required=True)
    parser.add_argument('--complete',action='store_true')
        
    #Attempt to open connection to the device - exit with error code 1 if not
    try:
        device = ids_interface.Connection()
        
        if not device.connected:
            print_and_log("Could not connect to Device")
            sys.exit(1)
    except Exception as e:
        print_and_log("Could not connect to Device")
        print_and_log(*traceback.format_exception(e))
        sys.exit(1)
    
    try:
        sensor = ms5837.MS5837_30BA()
        if not sensor.init():
            print_and_log("Could not connect to Pressure Sensor")
            sys.exit("Could not connect to Pressure Sensor")
        
        sensor.setFluidDensity(ms5837.DENSITY_SALTWATER)
    except Exception as e:
        print_and_log("Could not connect to Pressure Sensor")
        print_and_log(*traceback.format_exception(e))
        sys.exit("Could not connect to Pressure Sensor")
    
    def get_depth() -> float:
        try:
            sensor.read()
            depth : float = sensor.depth()
        except:
            print_and_log("Pressure Sensor Not Responding - setting depth to 0.0")
            depth : float = 0.0
        return depth
    
    def get_pressure() -> float:
        try:
            sensor.read()
            pressure : float = sensor.pressure()
        except:
            print_and_log("Pressure Sensor Not Responding - setting depth to 0.0")
            pressure : float = 0.0
        return pressure
      
      
    def get_temp() -> float:
        try:
            sensor.read()
            temp : float = sensor.temperature()
        except:
            print_and_log("Pressure Sensor Not Responding - setting temp to 0.0")
            temp : float = 0.0
        return temp
    
    def save_image_data(image:Cam_Image, filename):

        group = str(image.integration_time)
        if image.auto:
            group = "auto"
            
        image_data = [group, image.time_string(format="%Y-%m-%d %H:%M:%S"), image.integration_time, image.integration_time/1000000, image.cam_temp, get_temp(), get_pressure(), image.depth, image.inner_fraction_white, image.outer_fraction_white, image.corner_fraction_white,
                           *image.inner_avgs, *image.outer_avgs, *image.corner_avgs, image.relative_luminance, image.unscaled_absolute_luminance]
        
        new_file = False
        
        with open(filename, "r") as file:
            new_file = len(file.read()) == 0
        
        with open(filename, "a") as file:
            if new_file:
                file.write(f"group, timestamp, integration_time, integration_time_secs, camera_temperature_C, sensor_temp_C, pressure_mbar, depth_M, inner_saturated_pixels, outer_saturated_pixels, corner_saturated_pixels, {','.join([f'inner_pixel_average_{index}' for index, _ in enumerate(image.inner_avgs)])}, {','.join([f'outer_pixel_average_{index}' for index, _ in enumerate(image.outer_avgs)])}, {','.join([f'corner_pixel_average_{index}' for index, _ in enumerate(image.corner_avgs)])}, relative_luminance, absolute_luminance\n")
                
            
            file.write(','.join(str(item) for item in image_data))
            file.write('\n')

    def capture_image(integration_time_secs:float=None, gain:float=None, auto:bool=False):
        
        nonlocal current_session
        nonlocal current_routine
        nonlocal csv_filepath
        
        
        print_and_log(f"Capturing Image #{current_routine.image_count} - Integration Time : {integration_time_secs}s")
        

        if gain is not None:
            device.gain(gain) #Change device gain if it is passed 
        
        device.node("AcquisitionMode").SetCurrentEntry("SingleFrame")
            
        #Switch to auto-adjust integration time mode if integration time is 0 or None
        #Otherwise, set the integration time to the passed value.
        if integration_time_secs == 0 or integration_time_secs is None:
            auto = True
        else:
            device.exposure_time(seconds=integration_time_secs)
            
        try:    
            image: Cam_Image = current_session.run_and_log(lambda: device.capture_image(auto=auto))
            
            image.set_depth(get_depth())
            current_session.add_image(image)
            save_image_data(image, csv_filepath)
            
            print_and_log(f"Captured Image #{current_routine.image_count}")
        except Exception as e:
            print_and_log("Error Capturing Image")
            print_and_log(traceback.format_exc(e))
        
   
    

    # Parse command line arguments
    args = parser.parse_args()

    # Access the values of named arguments
    routine_name:str = args.routine
    session_name:str = args.session


    print_and_log(f'Routine Name: {routine_name}')
    print_and_log(f'Session Name: {session_name}')
    

        #Set the location of the routine files
    routine_dir=DATA_DIR / "routines"
    
    current_routine: routine.Routine = None
    
    #For each text or yml file in the routine directory check if it can be parsed as a Routine 
    #If it can and the name matches the passed in routine argument, set that as the routine to be used. 
    #When creating the routine, pass it the get_device_image function as its capture function.
    #Otherwise a dummy function is used which does not connect to the camera
    
    
    try:
        current_routine = routine.from_file(routine_name, capture_function=capture_image)
    except:
        for filename in os.listdir(routine_dir):
            if filename == routine_name:
                try:
                    current_routine = routine.from_file(Path(routine_dir) / filename, capture_function=capture_image)
                    break
                except Exception as e:
                    pass
            if filename.rsplit(".",1)[1].lower() in ["txt", "yaml", "yml"]:
                try:
                    this_routine = routine.from_file(Path(routine_dir) / filename, capture_function=capture_image)
                    if this_routine.name.replace(" ", "_") == routine_name.replace(" ", "_"):
                        current_routine = this_routine
                        break
                except Exception as e:
                    print_and_log(f"Routine file: {routine_dir}/{filename}")
                    print_and_log(traceback.format_exc(e))
                    print_and_log("###############")
                    continue

    #If no matching routine can be found, log an error and exit
    if current_routine is None:
        print_and_log(f"Routine {routine_name} does not exist.\nMake sure routine name has no spaces\n Exiting.")
        log_error()
        sys.exit(1)
    



    #Set location of the session list file (It's in json format)
    session_list_file= DATA_DIR / "sessions" / "session_list.json"
    
    #Set empty variables to fill with session info
    session_path: Path = None
    current_session: session.Session = None  
    new_session = False
    session_dict:dict = None
    
    try:
        with open(session_list_file, mode="r") as session_list:
            #Open the session list and parse the json data into a dict object 
            session_dict = json.load(session_list)
            
            #Check if a session of the specified name is in the session list
            if session_name in session_dict:
                #If it is get the session directory path and load the session from the file.
                session_path = Path(session_dict[session_name]['directory_path']) / session_name.replace(" ", "_")
                if session_path is not None and session_path.exists():
                    print_and_log("Session Exists")
                    current_session = session.from_file(session_path)
                    current_session.print_info()
            else:
                #If the session is not in the list, make a new session with that name. Session info such as coordinates/location
                # will have to be added later in the console interface
                print_and_log(f"Session {session_name} not found")
                print_and_log("Creating new session...")
                new_session = True
                
    except:
        print_and_log("Could not open Session List")
        new_session = True
        session_dict = {}
        
    #If a new session was created, add it to the session list file.
    if new_session:
        current_session = session.Session(name=session_name, directory=DATA_DIR / "sessions")
        with open(session_list_file, mode="w") as session_list:
            session_dict.update({current_session.name: 
                                    {"start_time":current_session.time_string(),
                                        "coords" : current_session.coords,
                                        "directory_path": str(current_session.directory_path),
                                        "images" : 0
                                        }
                                    })
            json.dump(session_dict, session_list, indent=4)
        
        print_and_log(f"New Session Created in {current_session.directory_path}")
    

    Path("./image_data").mkdir(parents=True, exist_ok=True)
    
    run_number = 0
    
    
    while os.path.exists(current_session.session_directory() / f"run_{run_number}.csv"):
        run_number += 1
    
    csv_filepath = current_session.session_directory() / f"run_{run_number}.csv"
    
    open(csv_filepath, "w").close()
    
  
            
    print_and_log(f"Running routine {current_routine.name}...")
    print_and_log(current_routine.to_string())
    
    #Run routine loop
    #The routine uses a "tick" system. 
    #
    #A while loop is started, and each "tick" the object checks the time since the routine 
    # started and when the next capture should be to automatically capture photos
    # using the settings defined in the routine file.
    # Each tick returns a dict object with:
    #               - a boolean "complete" property which is False until the routine is completed.
    #               - an "image" property which is None unless an image was captured with that tick, in which case it is a Cam_Image object
    #               - an "Image count" property which has the number of images captured so far in this run of the routine.
    
    

    if not os.path.exists(PIPE_IN_FILE):
        os.mkfifo(PIPE_IN_FILE)
        
    if not os.path.exists(PIPE_OUT_FILE):
        os.mkfifo(PIPE_OUT_FILE)
    

    
    device.node("ExposureAuto").SetCurrentEntry("Off")
    
    complete = False

    check_time_long = time()
    check_time_short = time()
    
    consecutive_error_count = 0
    in_pipe_fd = os.open(PIPE_IN_FILE, os.O_RDONLY | os.O_NONBLOCK)
    
    def write_to_pipe(message:str):
        try:
            
            out_pipe_fd = os.open(PIPE_OUT_FILE, os.O_WRONLY | os.O_NONBLOCK)
            with os.fdopen(out_pipe_fd, "w") as out_pipe:
                out_pipe.write(message)
            os.close(out_pipe_fd)  
            print_and_log("Successfully passed message " + message)
        except OSError:
            pass
        except Exception as e:
            print_and_log("Error passing message to named pipe")
            print_and_log(traceback.format_exc(e))
        
    
    
    with os.fdopen(in_pipe_fd) as in_pipe:
        while not complete:
            try:

                # Check for stop message
                message = in_pipe.read()
                if message:
                    
                    if message == "STOP":
                        current_routine.stop_signal = True
                        print_and_log("Received STOP Message")
                        if current_routine.capturing_image:
                            print_and_log("Waiting for image capture to finish...")
                        else: 
                            print_and_log("Stopping")
                        for i in range(10):
                            write_to_pipe("STOPPING")
                            sleep(0.2)
                    else:
                        print_and_log("Received Message: ", message)
                        
                        

                
                if not current_routine.stop_signal:   
                    if time() - check_time_long > 120:
                        print_and_log(f"Device Temp: {device.get_temperature()}°C  Depth: {get_depth():.2f}m Pressure Sensor Temp: {get_temp():.2f}°C")
                        check_time_long = time()
                        
    
                if time() - check_time_short > 1:
                    check_time_short = time()
                    message = f"Routine: {current_routine.name}\nSession: {current_session.name}\nRuntime: {str(timedelta(seconds=int(current_routine.run_time)))}\nImages Captured: {current_routine.image_count}"
                    if current_routine.stop_signal:
                        message  += "STOPPING\n"
                    write_to_pipe(message)

                tick_result = current_routine.tick()
                complete = current_routine.complete
                consecutive_error_count = 0
                
                
                
            except Exception as e:
                print_and_log("Tick Error")
                print_and_log(traceback.format_exception(e))

                consecutive_error_count += 1
                
                print_and_log("Error count: ", consecutive_error_count)
                if consecutive_error_count > 5:
                    print_and_log("Too many consecutive tick errors. Exiting")
                    sys.exit("Too many consecutive tick errors.")
                    
    
    print_and_log(f"Complete at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
#Wrapper code for running this script.
#Exits with exit code 0 if completed successfully, or 1 if there is an unhandled exception.
if __name__ == '__main__':
    try:
        main()
        sys.exit(0)
    except argparse.ArgumentError as e:
        # Print the provided arguments if there is an error
        print(f'Error parsing command line arguments: {e.argument_name}')
        print(e)
        sys.exit(1)
    except Exception as e:
        traceback.print_exc(e)
        sys.exit(1)