import argparse
from pathlib import Path
import json
import os
from dotenv import load_dotenv
import traceback
import sys
from datetime import datetime
from time import time
from contextlib import contextmanager


import routine
import session
import ids_interface
from cam_image import Cam_Image

load_dotenv()

DATA_DIR = Path(os.environ.get("DATA_DIRECTORY"))

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
        
      
    def capture_image(integration_time_secs:float=None, gain:float=None, auto:bool=False):
        
        nonlocal current_session
        nonlocal current_routine
        
        
        if gain is not None:
            device.gain(gain) #Change device gain if it is passed 
            
        #Switch to auto-adjust integration time mode if integration time is 0 or None
        #Otherwise, set the integration time to the passed value.
        if integration_time_secs == 0 or integration_time_secs is None:
            auto = True
        else:
            device.exposure_time(seconds=integration_time_secs)
            
            
        image: Cam_Image = current_session.run_and_log(lambda: device.capture_image(auto=auto))
        
        
        print_and_log(f"Captured Image #{current_routine.image_count}")
        
        
                    
        
        return image
   
    

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
                        continue

    #If no matching routine can be found, log an error and exit
    if current_routine is None:
        print_and_log(f"Routine {routine_name} does not exist.\nMake sure routine name has no spaces\n Exiting.")
        sys.exit(1)
    



    #Set location of the session list file (It's in json format)
    session_list_file= DATA_DIR / "sessions" / "session_list.json"
    
    #Set empty variables to fill with session info
    session_path: Path = None
    current_session: session.Session = None  
    new_session = False
    session_dict:dict = None
    

    with open( session_list_file, mode="r") as session_list:
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
            current_session = session.Session(name=session_name, directory=DATA_DIR / "sessions")
    
    #If a new session was created, add it to the session list file.
    if new_session:
        with open(session_list_file, mode="w") as session_list:
            session_dict.update({current_session.name: 
                                    {"start_time":current_session.time_string(),
                                        "coords" : current_session.coords,
                                        "directory_path": str(current_session.directory_path),
                                        "images" : 0
                                        }
                                    })
            json.dump(session_dict, session_list, indent=4)
    

    Path("./image_data").mkdir(parents=True, exist_ok=True)
    
    run_number = 0
    while os.path.exists(DATA_DIR /"sessions" / f"{current_session.name}" / f"run_{run_number}.csv"):
        run_number += 1
    
    filename = DATA_DIR / "sessions" / f"{current_session.name}" / f"run_{run_number}.csv"
    
    open(filename, "w").close()
    
        
    def save_image_data(image:Cam_Image):
        nonlocal filename
        
        image_data = [image.integration_time/1000000, image.temp, image.inner_fraction_white, image.outer_fraction_white, image.corner_fraction_white,
                           *image.inner_avgs, *image.outer_avgs, *image.corner_avgs]
        
        new_file = False
        
        with open(filename, "r") as file:
            new_file = len(file.read()) == 0
        
        with open(filename, "a") as file:
            if new_file:
                file.write(f"int_time_s temp_C inner_wf outer_wf corner_wf {' '.join([f'inner_avg_{index}' for index, _ in enumerate(image.inner_avgs)])} {' '.join([f'outer_avg_{index}' for index, _ in enumerate(image.outer_avgs)])} {' '.join([f'corner_avg_{index}' for index, _ in enumerate(image.corner_avgs)])}\n")
                
            
            file.write(' '.join(str(item) for item in image_data))
            file.write('\n')
            
            
            
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
    
    complete = False

    check_time = time()
    
    while not complete:
        try:
            if time() - check_time > 5:
                print_and_log(f"Device Temp: {device.get_temperature()}°C")
                check_time = time()
            tick_result = current_routine.tick()
            complete = tick_result["complete"]
            img:Cam_Image = tick_result["image"]
            
            
            
            #If the tick returns with a Cam_Image object, add it to the session (Which will save it 
            # to the session directory and add its info to the session log).
            if img is not None:
                current_session.add_image(img)
                save_image_data(img)
                
        except Exception as e:
            print_and_log("Tick Error")
            print_and_log(*traceback.format_exception(e))

    
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