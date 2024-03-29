import traceback
import json
from pathlib import Path
import os, sys

import time

import routine
import threading
from dotenv import load_dotenv

try:
    from simple_term_menu import TerminalMenu
    unix = True
except:
    print("Program Can Only Run on Linux or Mac OS X")
    sys.exit(1)
    

import ids_interface
import cam_image
import session

DATA_DIR = Path(os.environ.get("DATA_DIRECTORY"))

class Console_Interface:

    def __init__(self) -> None:
        """Create a console interface object to start controlling a camera device
        """        
        print("Console Interface for Camera Control")
        self.ssh_mode = "SSH_CONNECTION" in os.environ
        if self.ssh_mode:
            os.environ['DISPLAY'] = ':0'
        clear_console()

        self.running = False
        #TODO: Add and change default directory
        self.ids_connection:ids_interface.Connection = None
        self.session :session.Session = None
        self.sessions_dict = {}
        
        self.auto_integration = False
        session_list_path = DATA_DIR / "sessions" / "session_list.json"
        if session_list_path.exists():
            with open(session_list_path) as sessions_json:
                try:
                    self.sessions_dict = json.load(sessions_json)
                except:
                    pass
        self.main_loop()       


        

    def main_loop(self):
        """Loop that shows the main menu
        """        
        try:

            self.running = True

            while self.running:
                self.running = self.opening_menu()
        except Exception as e:
            traceback.print_exc(e)    


    
    def opening_menu(self) -> bool:
        """Opening Menu from where sessions can be browsed or started

        Returns:
            bool: boolean. If this is passed back to main loop as False, the program will close
        """  
        try:
            options = ["[n] Start New Recording Session"]
            if len(self.sessions_dict) > 0:
                options.append("Open Existing Session")
            options.append("[q] Quit")
            match get_menu_choice(options, title=f"IDS Device Control                SSH Mode: {'On' if self.ssh_mode else 'Off'}"):
                case "Start New Recording Session":
                    if self.create_session():
                        return self.session_menu()
                case "Open Existing Session":
                    if self.list_sessions_menu():
                        return self.session_menu()
                case "Quit":
                    return False
            return True
                
        except Exception as e:
            traceback.print_exc(e)
                
                
    def session_info_text(self) -> str:
        """# Session Info Text
            Builds a string with information about the current session and connected device
        Returns:
            str: Session information string
        """        
        line="\n====================================================\n"
        name_line = f"Session: {self.session.name} | {len(self.session.log['images'])} Images"
        
        info_line = f"Start Time: {self.session.time_string()}"
        dir_line = f"Directory: {str(self.session.directory_path / self.session.name.replace(' ', '_'))}"
        if self.session.coords != (None, None):
            info_line = f"{info_line} | Coords: {self.session.coords[0], self.session.coords[1]}"
        
        title = f"{name_line}\n{info_line}\n{dir_line}{line}"
        if self.ids_connection is not None:
                device_string = f"Device Connected: {self.ids_connection.info['Model']} Temperature:{self.get_temperature()}°C"
                device_settings = f"\n integration: {round(self.integration_time()/1000000, 5)}s (Auto-adjust: {['Off', 'On'][self.auto_integration]}) | Gain: {round(self.gain())}dB"
                title = f"{title}{device_string}{device_settings}"
        else:          
            title = f"{title}No Device Connected"
            
        title = f"{title}{line}"
        return title
                
    def view_image_details(self):
        """# View Image Details
        
        Shows list of images in current session and information about them
        #TODO: Add ability to add note to image
        """
        
        def get_image_details(number:str) -> str:
            """# Get Image Details
            
            Builds a string containing the details of the specified image.
            
            Used to show the image details in the status bar for the currently highlighted image

            Args:
                number (str): number of desired image in session

            Returns:
                str: string containing image details
            """            
            if number.startswith("["): #remove shortcut part of string
                number = number.split("] ", 1)[1]
            
            number = number.split(".", 1)[0] #get number part
            
            try:
                number = int(number)
            except:
                return "Back"
            
            if number > len(self.session.log["images"]):
                return "Back"
            
            image = self.session.log["images"][int(number)-1]
            #print(image)
            img_strings = []
            i = 0
            for key, value in image.items():
                img_strings.append(f"{key.ljust(35, '.')}{value}")
            
            return "\n".join(img_strings)
            
        if self.session is None:
            return False

        options = []
        for index, image in enumerate(self.session.log["images"]):
            image:cam_image.Cam_Image
            img_string = f"{str(image['number']).ljust(20, '.')} - {image['time']}"
            if index < 9:
                img_string = f"[{index+1}] {img_string}"
            options.append(img_string)
        options.append("[esc] Back")
            
        title = f"{self.session.name} Images"
        
        get_menu_choice(options=options, title = title, status_bar=lambda x: get_image_details(x) )
        
        return True
                
    def session_menu(self) -> bool:
        """# Session Menu
        Displays a menu with options for the currently open Session

        Returns:
            bool: _description_
        """        
        try:
            if self.session is None:
                return False
            
            title = self.session_info_text()
            
            options = []
            if len(self.session.log['images']) > 0:
                options.append("[d] View Session Image Details")
            if self.ids_connection is not None:
                options.extend( ["[c] Capture Image", "[r] Run Routine", "[t] Start auto-capture process", "[i] Set Integration Time", "[g] Set Gain"])
                
                if self.auto_integration:
                    options.append("[a] Turn off integration time auto-adjust")
                else:
                    options.append("[a] Turn on integration time auto-adjust")
                        
            else:
                options.extend(["Connect Device"])
                
            options.extend(["Close Session", "[q] Quit"])
            
            match get_menu_choice(options, title=title):
                case "Close Session":
                    self.session = None
                    return True
                case "View Session Image Details":
                    self.view_image_details()
                case "Capture Image":
                    self.capture_image()
                case "Run Routine":
                    self.select_routine()
                case "Start auto-capture process":
                    self.start_auto_capture()
                case "Set Integration Time":
                    new_exp = input("Enter new integration time in seconds: ")
                    self.integration_time(seconds=float(new_exp))
                case "Set Gain":
                    new_gain = input("Enter new gain (db) (between 1 and 16): ")
                    self.gain(new_gain)
                case "Connect Device":
                    self.open_connection()
                case "Turn on integration time auto-adjust":
                        self.auto_integration = True
                case "Turn off integration time auto-adjust":
                        self.auto_integration = False
                case "Quit":
                    self.session = None
                    return False
                
                    
                    
            return self.session_menu()
            
        except Exception as e:
            traceback.print_exc(e)
            
            
    def getchar():
        """Get character from stdin"""
        while 1:
            try:
                c = sys.stdin.read(1)
                break
            except IOError:
                try: time.sleep(0.001)
                except:  raise KeyboardInterrupt
        return c

    def control (self):
        """Waits for keypress"""
        start_time = time.time()
        last_time_printed = 0
        while self.running:
            c = Console_Interface.getchar().lower()
            if c=="q": 
                print("Quitting!")
                self.routine.complete = True
                self.running = 0
                break
        self.done += 1  
        
    def run(self):
        try:
            while self.running:
                tick_val = self.routine.tick()
                self.running = not tick_val["complete"]
                img = tick_val["image"]
                if img is not None:
                    self.session.add_image(img)
            print("Press Enter to return to session menu...")
            self.done+=1
        except Exception as e:
            traceback.print_exc(e)
            self.done+=1
            self.running=0
            
            
            
            
    def select_routine(self):
        

        routines = {}
        routine_names = []
        i = 0
        for filename in os.listdir(DATA_DIR / "routines"):
            if filename.rsplit(".",1)[1].lower() in ["txt", "yaml", "yml"]:
                current_routine = routine.from_file(DATA_DIR / "routines" / filename, capture_function=self.get_device_image)
                routines[current_routine.name] = current_routine
                name_str = ""
                if i < 10:
                    name_str = f"[{i}] "
                i+= 1
                name_str += current_routine.name
                routine_names.append(name_str)
        
        def get_short_string(array):
            if array.size > 1:
                return f"{array[0]}, {array[1]}, {array[2]}..."
            return f"{array[0]}"
        
        def routine_details(routine_name):
            try:
                current_routine:routine.Routine = routines[routine_name]
            except KeyError:
                return "Return to Session Menu"
            routine_str = f"{current_routine.name}\n"
            routine_str += f"Time limit: {current_routine.time_limit_secs}\n"
            routine_str += f"Num limit: {current_routine.number_limit}\n"
            routine_str += f"Repeat: {current_routine.repeat}\n"
            routine_str += f"Initial delay: {current_routine.initial_delay}\n"
            routine_str += f"Interval: {current_routine.interval_secs}\n"
            routine_str += f"Interval Mode: {current_routine.interval_mode}\n"
            routine_str += f"Integration time/times: " + get_short_string(current_routine.int_times) + "\n"
            routine_str += f"Gain setting/settings: " + get_short_string(current_routine.gains) 
            return routine_str

        
        routine_names.append("[q] Back")
        
        selected_routine = get_menu_choice(routine_names, title="Select Routine", status_bar=lambda x: routine_details(x))
        
        if selected_routine not in routines: 
            return True
        
        return routines[selected_routine]

            
    def run_routine(self):
        
        clear_console()
    
        self.routine = self.select_routine()
        clear_console()
        print(f"Running routine {self.routine.name}...")
        print("Type 'q' and hit Enter to stop")
        self.running = 1
        self.done = 0

        routine_thread = threading.Thread(target=self.run)
        control_thread = threading.Thread(target=self.control)

        routine_thread.start()
        control_thread.start()

        # Block the program not to close when threads detach from the main one:
        while self.running:
            try: time.sleep(0.2)
            except: self.running = 0
        # Wait for both threads to finish:
        while self.done!=2:
            time.sleep(0.001)

        return True


    def start_auto_capture(self):
        try:
            routine = self.select_routine()
            
            options = ["Start Routine", "Return to Session"]
            
            title = f"Auto Capture\nSettings:\nSession: {self.session.name}\nRoutine: {routine.name}\nStart Autocapture?\n(Camera will be temporarily unavailable during auto-capture)"
            
            
            choice = get_menu_choice(options, title=title)
            if choice == options[0]:
                self.close_connection()
                with open("process/process.txt", mode="w") as process_file:
                    process_file.writelines(f"--routine {routine.name}\n--session {self.session.name}\n")
                    
            
        except Exception as e:
            print("Error launching auto_capture")
            traceback.print_exc(e)
        
        
    def get_unique_session_name(self, name:str=None) -> str:
        """# Get Unique Session Name
        Loops until a session name is entered that is either valid or blank (in which case the new Session will be given a default name)
        If the name given is the same as an existing session, the user has the option to open that session or try again with a new unique name
        Args:
            name (str, optional): Name string entered by user. Defaults to None.

        Returns:
            str: A valid name, or '[open_session]' if an existing session has been opened
        """        
        if name not in self.sessions_dict:
            return name
        else:
            if confirm(f"Session with name {name} exists. Open this session?"):
                self.open_session(name)
                return "[open_session]"
        
        name = session.get_valid_name()
        
        return self.get_unique_session_name(name)
                
    def create_session(self, name:str=None) -> bool:
        if self.session is None:
            if name is None:
                name = self.get_unique_session_name()
                if name == "[open_session]":
                    return True
                    
            self.session = session.start_session(name=name)
            self.sessions_dict.update({self.session.name: 
                                        {"start_time":self.session.time_string(),
                                         "coords" : self.session.coords,
                                         "directory_path": str(self.session.directory_path),
                                         "images" : 0
                                         }
                                        })
            with open(DATA_DIR / "sessions" / "session_list.json", "w") as session_list:
                json.dump(self.sessions_dict, session_list, indent=4)
            return True
        else:
            print("Session is already running:")
            self.session.print_info()
            if confirm("Close this session and start a new one?"):
                self.session = None
                return self.create_session()
        return False
    
    def list_sessions_menu(self) -> bool:
        """# List Sessions Menu
        displays menu of existing sessions which a user can open.
        The status bar shows details of the highlighted session
        Returns:
            bool: True if a session has been opened, otherwise False
        """        
        options = []
        i = 0
        for key, value in self.sessions_dict.items():
            shortcut = ""
            if i < 10:
                shortcut = f"[{i}] "
            options.append(f"{shortcut}{key}")
            i += 1
        
        options.append("[esc] Back")
        
        def session_details(string:str)-> str:
            """Session Details
            Generates a string containing details of the session with the passed in name
            Used for generating the status bar in the sessions menu
            Args:
                string (str): name of desired session

            Returns:
                str: String containing details of session
            """            
            if string.startswith("["):
                string = string.split("] ")[1]
            if string in self.sessions_dict:
                start_time = self.sessions_dict[string]['start_time']
                coords = self.sessions_dict[string]['coords']
                coords_str = f"({coords[0]}, {coords[1]})"
                images_str = f"{self.sessions_dict[string]['images']} images"
                
                return f"{start_time} | Coordinates: {coords_str} | {images_str}"
            return "Back"
        
        option =  get_menu_choice(options, title="Open Existing Session", status_bar=lambda x: session_details(x))
        if option == "Back":
                return False
        
        self.open_session(option)
        return True
            

    
    def open_session(self, name:str=None, file_path:str=None) -> bool:
        """# Open Session
        set the current session to the specified one.
        If the name is in the session list, passes the corresponding directory path to the Session class,
        otherwise just passes the raw string along
        Args:
            name (str, optional): Name of session
            file_path (str, optional): Filepath of session

        Returns:
            bool: True if session is successfully opened, otherwise false
        """    
        try:    
            
            if (name is not None) + (file_path is not None) != 1:
                print("Must specify either file_path or name")
            if self.session is not None:
                print(f"Session {self.session.name} already open.")
                if name is not None:
                    if name != self.session.name:
                        if not confirm(f"Close this session and open session {name}?"):
                            return False
                if file_path is not None:
                    if not confirm(f"Close this session and open session at {file_path}?"):
                        return False
                return True
                    
            if name is not None:
                file_path = ""
                if name in self.sessions_dict:
                    file_path = Path(self.sessions_dict[name]['directory_path']) / name.replace(' ', "_")
                    
            self.session = session.from_file(file_path)
            return True
        except Exception as e:
            traceback.print_exc(e)
            return False
              
    def open_connection(self) ->bool:
        try:
            self.ids_connection = ids_interface.Connection()
        
            return True
        except Exception as e:
            traceback.print_exc(e) 
            return False
            

    def check_start_session(self) -> bool:
        if self.session is None:
            
            if confirm("No Session Started - Start new Session?", default=True):
                self.create_session()
                return True
            else:
                print("You must start a session before capturing data")
                print("Use command 'session -create' to start a session")
                return False  

        else:
                return True
                
            
    def check_open_connection(self):
        if self.ids_connection is None:
            if confirm("No Device Connected - Attempt Connection?", default=True):
                return self.open_connection()
            else:
                print("Device not connected")
                print("Use command 'connect' to open a connection")
                return False
            
        
        return True
    
    def get_device_image(self, integration_time_secs:float=None, gain:float=None, auto:bool=False):
        try:
            if integration_time_secs is not None:
                self.integration_time(integration_time_secs)
            if gain is not None:
                self.gain(gain)
                
            if integration_time_secs == 0 or auto:
                self.auto_integration = True
                
            image = None
            
            
            
            if False:
                self.integration_time(seconds=0.05)
                image_correctly_exposed = False
                while not image_correctly_exposed:
                    image = self.ids_connection.single_frame_acquisition()
                    target_fraction = 0.01
                    target_margin = 0.005
                    overexposed_difference = check_integration(image=image, target_fraction=target_fraction)
                    if abs(overexposed_difference) <= target_margin:
                        image_correctly_exposed = True
                    else:
                        print(f"Incorrectly Exposed at {image.integration_time/1000000}s")
                        print(f"Fraction of pixels overexposed: {image.fraction_white}")
                        print(f"Target Fraction: {target_fraction}")

                        
                        adjustment_factor = min(1.5, max(0.5, 1 - (image.fraction_white-target_fraction)/target_fraction  ))
                        
                        print("Adjustment factor: ", adjustment_factor)
                        new_integration  = image.integration_time*adjustment_factor
                        
                        print(f"Changing integration time to { self.integration_time(microseconds=new_integration)/1000000}s")

                    
        
            else:
                if self.auto_integration:
                    self.ids_connection.quiet_mode = False
                image = self.ids_connection.capture_image(auto=self.auto_integration)    
                self.ids_connection.quiet_mode = True            
            
            return image
        
        except Exception as e:
            traceback.print_exc(e)
            return None
        
    def capture_image(self) -> bool:
        try:
           
            if self.check_start_session() and self.check_open_connection() : #check a session is started and a device is connected


                image = self.get_device_image()
                if image is not None:   
                    self.session.add_image(image)
                    self.sessions_dict[self.session.name]["images"] += 1
                    return True

            return False
        except Exception as e:
            traceback.print_exc(e)  
            return False  
        
    
        
    def close_connection(self) -> bool:
        try:
            print("Closing connection...")
            if self.ids_connection is not None:
                close = self.ids_connection.close_connection()
                self.ids_connection = None
                print("Connection closed")
                return close
        
            else:
                print("No device connected")
                return True
            
        except Exception as e:
            traceback.print_exc(e)    
            return False
    
    def get_temperature(self):
        if not self.check_open_connection():
            return False
        temperature = self.ids_connection.get_temperature()
        return temperature
    
    def integration_time(self, seconds:float=None, microseconds:int=None):
        
        if not self.check_open_connection():
            return False

        value = None
        multiplier = 1000000
        
        set = False
        if seconds is not None:
            if microseconds is not None:
                print("Can't Set integration time in seconds and microseconds in same call")
                
            set = True
            value = seconds
            multiplier = 1000000

        if microseconds is not None:
            set = True
            value = microseconds
            multiplier = 1
            
        
        if set:
            new_value_microsecs = int(value*multiplier)
            set_value_microsecs = self.ids_connection.exposure_time(new_value_microsecs)
            return set_value_microsecs
        else:
            integration_time_microsecs = self.ids_connection.exposure_time()
            return integration_time_microsecs
    
    def gain(self, new_value:float=None):
        if not self.check_open_connection():
            return False
        
        if new_value is not None:
            new_gain = self.ids_connection.gain(new_value)

        return self.ids_connection.gain()


def get_menu_choice(options, **kwargs):
    menu = TerminalMenu(options, **kwargs)
    
    clear_console()
    index = menu.show()
    
    if index is None:
        return index
    
    choice:str = options[index]
    if choice.startswith("["):
        choice = choice.split("] ", 1)[1]
    return choice
    

def confirm(message:str, default:bool=None) -> bool:
    options = ""
    if default is None:
        options = "[y/n]"
    else:
        if default:
            options = "[[y]/n]"
        elif not default:
            options = "[y/[n]]"
            
    response = input(f"{message} {options}").lower()
        
    if response == "":
        if default is None:
            return confirm(message, default)
        else:
            return default
    elif response in ["yes", "y"]:
        return True
    elif response in ["no", "n"]:
        return False
    else:
        blank_opt = ""
        if default is not None:
            blank_opt = ", or leave blank for default"
        print(f"Invalid response - please enter 'y' or 'n'{blank_opt}.")
        return confirm(message, default)

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear -x')
    

def check_integration(image:cam_image.Cam_Image, target_fraction:float) -> float:
    return target_fraction - image.fraction_white

if __name__ == "__main__":
    ui = Console_Interface()
    sys.exit(0)
    
