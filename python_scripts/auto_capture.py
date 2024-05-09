import argparse
from pathlib import Path
import json
import os
from dotenv import load_dotenv
import traceback
import sys
from datetime import datetime, timedelta
from time import time, sleep


  


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
    stored_strings = []
    
    current_session: session.Session = None
    current_routine: routine.Routine = None
    
    

        
    def print_and_log(*args,  error=False, **kwargs):
        """Function for logging output of this script. If this is run from a systemd service the output should go to the RPi logs 
        to be read with journalctl, but this also writes to a file in the session which is loaded. If there is no session loaded 
        it saves the output until one is opened and then writes it.
        """
        try:
               
            
            str_args = ""
            for arg in args:
                if isinstance(arg, str):
                    str_args+=arg
                else:
                    str_args+=str(arg)
                    
            nonlocal current_session
            nonlocal stored_strings
            if error:
                kwargs['file'] = sys.stderr
            print(*args, **kwargs)
            if current_session is not None:
                if stored_strings:
                    current_session.output(stored_strings, error=error)
                    stored_strings = []
                    
                current_session.output(str_args, error=error)
                
            else:
                stored_strings.append([str_args, datetime.now()])
        except Exception as e: 
            #print(f"stderr: {sys.stderr}")
            #print(f"Kwargs: {kwargs} - Args: {args}", file=sys.stderr)
            print(traceback.format_exception(e), file=sys.stderr)
            #sys.exit("Error printing")

    def log_error(error:Exception=None, message:str=None):
        
        nonlocal stored_strings
        nonlocal current_session
        try:
            traceback.print_exception(error,file=sys.stderr)
            string = "ERROR: "
            if message is not None:
                string += message

            if error is not None:
                string += "\n"
                string = "".join(traceback.format_exception(error))
            string += "\n"
            print(string, file=sys.stderr)
            print_and_log(string)
            if current_session is None:
                with open(DATA_DIR / "sessions" / "error_log.log", "a") as log_file:
                    log_file.write("---------------------------------------------------\n")
                    log_file.write(string)
        except Exception as e:
            traceback.print_exception(e,file=sys.stderr)
        

    def central_log(*args):
        with open(DATA_DIR / "sessions" / "central_log.log", "a") as log_file:
            log_file.write("---------------------------------------------------\n")
            string = "".join(args)
            log_file.write(string)

          

    def flush_stored_strings():
       nonlocal stored_strings 
       for timestamp, string in stored_strings:
           central_log(f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')}: {string}")

    
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
            log_error(message="Could not connect to Device")
            sys.exit(1)
    except Exception as e:
        print_and_log("Could not connect to Device")
        log_error(e)
        sys.exit(1)
    

    
    try:
        sensor = ms5837.MS5837_30BA()
        if not sensor.init():
            log_error(message="Could not connect to Pressure Sensor")
            sys.exit("Could not connect to Pressure Sensor")
        
        sensor.setFluidDensity(ms5837.DENSITY_SALTWATER)
    except Exception as e:
        print_and_log("Could not connect to Pressure Sensor")
        log_error(e)
        sys.exit("Could not connect to Pressure Sensor")
    
    def get_depth(retry:bool=False) -> float:
        try:
            sensor.read()
            depth : float = sensor.depth()
        except:
            if retry:
                sleep(0.1)
                depth = get_depth()
            else:
                print_and_log("Pressure Sensor Not Responding - setting depth to 0.0")
                depth : float = 0.0
        return depth
    
    def get_pressure(retry:bool=False) -> float:
        try:
            sensor.read()
            pressure : float = sensor.pressure()
        except:
            if retry:
                sleep(0.1)
                pressure = get_pressure()
            else:
                print_and_log("Pressure Sensor Not Responding - setting pressure to 0.0")
                pressure : float = 0.0
        return pressure
      
      
    def get_temp(retry:bool=False) -> float:
        try:
            sensor.read()
            temp : float = sensor.temperature()
        except:
            if retry:
                sleep(0.1)
                temp = get_temp()
            else:
                print_and_log("Pressure Sensor Not Responding - setting temp to 0.0")
                temp : float = 0.0
        return temp
    

    def capture_image(integration_time_secs:float=None, gain:float=None, auto:bool=False):
        try:
            
            nonlocal current_session
            nonlocal current_routine
            
            exposure_time = device.exposure_time()/1e6
            image_string = f"Capturing Image #{current_session.image_count + current_session.queue_length}(Routine image#{current_routine.image_count}) - Integration Time : {integration_time_secs}s"
            if auto:
                image_string += "- Auto Exposure"
            print_and_log(image_string)
            

            if gain is not None:
                device.gain(gain) #Change device gain if it is passed 
            

            #Switch to auto-adjust integration time mode if integration time is 0 or None
            #Otherwise, set the integration time to the passed value.
            if integration_time_secs == 0 or integration_time_secs is None or auto:
                auto = True
            else:
                exposure_time = device.exposure_time(seconds=integration_time_secs)/1e6
                print_and_log(f"Set Exposure Time to {exposure_time}s")
              
            capture_successful = False
            image = None
            attempt_no = 0
            desired_exposure_time = integration_time_secs*1e6 if not auto else None
            while not capture_successful:
                print_and_log("Capturing...")
                
                image: Cam_Image = device.capture_frame(return_type=ids_interface.Resources.CAM_IMAGE, desired_exposure_time_microseconds=desired_exposure_time)
                if image.image is None:
                    print_and_log("Capture failed - retrying...")
                    continue
                print_and_log("Capture Complete")
                image.set_depth(get_depth(retry=True))
                image.set_pressure(get_pressure(retry=True))
                image.set_environment_temperature(get_temp(retry=True))
                image.set_auto(auto)
                current_session.add_image_to_queue(image)
                print_and_log(f"Added to Queue - Queue size: {current_session.queue_length}")
                if auto:
                    print_and_log("Auto")
                    attempt_no += 1
                    
                    capture_successful = image.correct_saturation
                    print_and_log("capture_successful: ", image.correct_saturation)
                    if not capture_successful:
                        new_exposure_time = ids_interface.calculate_new_exposure(current_exposure_time=image.integration_time/1e6, saturation_fraction=image.inner_saturation_fraction)
                        
                        print_and_log(f"Attempt {attempt_no}: Incorrect Saturation Fraction of {round(image.inner_saturation_fraction, 3)} - at {image.integration_time/1e6}s - trying at {new_exposure_time}s")
                        device.exposure_time(seconds=new_exposure_time)
                        exposure_time = new_exposure_time
                        desired_exposure_time = exposure_time*1e6
                    else:
                        print_and_log(f"Attempt {attempt_no}: Correct saturation at {image.integration_time/1e6}s")
                        capture_successful = True
                else:
                    capture_successful = True

                        
            
            print_and_log(f"Captured Image #{current_routine.image_count}")
            print_and_log(f"Timestamp: {image.time_string('%Y-%m-%d %H:%M:%S')}")
            print_and_log(f"Integration Time: {image.integration_time/1e6}s ")
            
        except Exception as e:
            print_and_log(f"Error Capturing Image {current_routine.image_count}")
            log_error(e)
        

    

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
                    log_error(e)
                    continue

    #If no matching routine can be found, log an error and exit
    if current_routine is None:
        print_and_log(f"Routine {routine_name} does not exist.\nMake sure routine name has no spaces\n Exiting.", error=True)
        log_error(Exception(f"Routine {routine_name} not found"))
        sys.exit(1)
    



    #Set location of the session list file (It's in json format)
    session_list_file= DATA_DIR / "sessions" / "session_list.json"
    
    #Set empty variables to fill with session info
    session_path: Path = None
    current_session: session.Session = None  
    new_session = False
    session_dict:dict = None
    try:
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
                        print_and_log(f"{current_session}")
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
            
            print_and_log(f"New Session Created in {current_session.parent_directory}")
            
    except Exception as e:
        log_error(e)
        flush_stored_strings()
        sys.exit("Exited - Could not open session")
  
  
  

            
    print_and_log(f"Running routine {current_routine.name}...")
    print_and_log(str(current_routine))
    
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
    
    device.gain(1)
    device.change_sensor_mode("Default")
    device.exposure_time(seconds=current_routine.int_times[0])
    
    device.node("AcquisitionMode").SetCurrentEntry("Continuous")
    device.start_acquisition()
    
    device.node("ExposureAuto").SetCurrentEntry("Off")
    device.node("GainAuto").SetCurrentEntry("Off")
    
    sleep(0.5)
    complete = False


    
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
            log_error(e)
        
    check_time_long = time()
    check_time_short = time()
    
    current_session.start_processing_queue()

    
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
                    if time() - check_time_long > 300:
                        print_and_log(f"Device Temp: {device.get_temperature()}°C  Depth: {get_depth():.2f}m Pressure Sensor Temp: {get_temp():.2f}°C")
                        check_time_long = time()

    
                if time() - check_time_short > 1:
                    check_time_short = time()
                    try:
                        message = f"Routine: {current_routine.name}\nSession: {current_session.name_no_spaces}\nRuntime: {str(timedelta(seconds=int(current_routine.run_time)))}\nImages Captured: {current_routine.image_count}\nImage Save Queue Size: {current_session.queue_length}\n"
                        if current_routine.stop_signal:
                            message  += "\nSTOPPING\n"
                        write_to_pipe(message)
                    except Exception as e:
                        pass

                #current_session.run_and_log(current_routine.tick)
                current_routine.tick()
                
                
                
                complete = current_routine.complete
                consecutive_error_count = 0
                
                
                
            except Exception as e:
                print_and_log("Tick Error")
                log_error(e)

                consecutive_error_count += 1
                
                print_and_log(f"Error count: {consecutive_error_count}")
                if consecutive_error_count > 5:
                    print_and_log("Too many consecutive tick errors. Exiting")
                    
                    sys.exit("Too many consecutive tick errors.")
    print_and_log(f"Completion Reason: {current_routine.stop_reason}")
    device.stop_acquisition()
    current_session.stop_processing_queue()
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
        traceback.print_exception(e)
        sys.exit(1)