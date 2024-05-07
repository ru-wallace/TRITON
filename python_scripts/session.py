from PIL import Image
from PIL.PngImagePlugin import PngInfo
from pathlib import Path
import numpy as np
import json
import cam_image
import sys, os
from dotenv import load_dotenv
import traceback
import threading, queue

from datetime import datetime

from contextlib import contextmanager

@contextmanager
def redirect_output(fileobj):
    old = sys.stdout
    sys.stdout = fileobj
    try:
        yield fileobj
    finally:
        sys.stdout = old
        
load_dotenv()

DATA_DIR =  Path(os.environ.get("DATA_DIRECTORY"))
PRETTY_FORMAT = "%Y-%m-%d %H:%M:%S"
FILEPATH_FORMAT = "%Y_%m_%d__%H_%M_%S"
        

class Session:
    
    def __init__(self, name:str|None=None, coords:tuple[float|None] = (None,None), start_time:datetime|None = None, directory:str|None=None, images:dict=None) -> None:
        try:
            
            if start_time is None:
                self.start_time:datetime = datetime.now()
            else:
                self.start_time = start_time 
            
            
            if name is None or name == "":
                self.name:str = f"session_{self.time_string(FILEPATH_FORMAT)}"
            else:
                self.name:str = name.strip()
                
            self.name_no_spaces = self.name.replace(" ", "_")
            self.coords:tuple[float|None] = coords
                

                
            if directory is None:
                self.parent_directory :Path =DATA_DIR / "sessions"
            else:
                self.parent_directory :Path = Path(directory)
                
            self.directory = self.parent_directory / self.name_no_spaces
            self.image_directory = self.directory / "images"
            self.csv_file_path = self.directory / "data.csv"
            self.json_file_path = self.directory / "session.json"
            self.session_list_file = self.parent_directory / "session_list.json"
            
            self.image_directory.mkdir(parents=True, exist_ok=True)
                      
           
            self.images:list[cam_image.Cam_Image]=[]
            
            if images is None:
                self.last_updated = self.start_time
            else:
                self.last_updated = datetime.strptime(max(images, key= lambda image: int(image['number']))['time'], PRETTY_FORMAT)
                self.images = images
                
            
            self.log : dict = {"name" : self.name,
                                "start_time" : self.start_time.strftime(PRETTY_FORMAT),
                                "last_updated": self.last_updated.strftime(PRETTY_FORMAT),
                                "coords" : str(self.coords[0])+", " + str(self.coords[1]),
                                "path" : str(self.directory),
                                "images" : images
                                }
            
                
            self.write_to_log()
            
            self.image_queue:queue.Queue = queue.Queue()
            self.processing_images = False   
            
            
        except Exception as e:
            traceback.print_exc(e)
    
    @property
    def details(self) -> dict:
        return {"name" : self.name,
                    "start_time" : self.start_time.strftime(PRETTY_FORMAT),
                    "last_updated": self.last_updated.strftime(PRETTY_FORMAT),
                    "coords" : str(self.coords[0])+", " + str(self.coords[1]),
                    "path" : str(self.directory),
                    "images" : self.image_count
                    
                    }
    
    
    
    def session_directory(self) -> Path:
        return self.parent_directory / f"{self.name.replace(' ', '_')}"
                        
    def time_string(self, format:str="%Y-%m-%d %H:%M:%S") -> str:
        return datetime.strftime(self.start_time, format)
    
    def add_image(self, image:cam_image.Cam_Image)-> int:
        image.number = self.image_count
        self.images.append(image)
        return image
    
    @property
    def image_count(self) -> int:
        return len(self.images)
    
    def add_image_to_queue(self, image:cam_image.Cam_Image):
        self.image_queue.put(image)
            
    def start_processing_queue(self):
        self.processing_images = True
        process_thread = threading.Thread(target=self.process_image_queue)
        process_thread.start()
    
    def finish_processing_queue(self):
        self.image_queue.join()
        self.processing_images = False
    
    def process_image_queue(self, image:cam_image.Cam_Image) -> bool:
        while self.processing_images:
            image = self.image_queue.get()                
            try:
                image = self.add_image(image)
            except:
                self.output("Warning: couldn't add image to session.images", error=True)
                self.output(traceback.format_exc(e), error=True)
            
            try:
                self.update_session_list()
            except:
                self.output("Warning: couldn't update session_list", error=True)
                self.output(traceback.format_exc(e), error=True)
                                            
            
            try:        
                image_location = self.image_directory/ f"{self.name_no_spaces}_{str(image.number).rjust(3, '0')}.png"
                
                image.save(image_location, additional_metadata={"session" : self.name})
            except:
                self.output(f"Warning: couldn't save image {self.image_count-1}", error=True)
                self.output(traceback.format_exc(e), error=True)
                                            
            try:    
                self.write_to_log()
            except:
                self.output("Warning: couldn't write to log", error=True)
                self.output(traceback.format_exc(e), error=True)
            try:                                
                self.write_to_csv(image)
            except:
                self.output("Warning: couldn't add image details to csv", error=True)
                self.output(traceback.format_exc(e), error=True)
            
            self.image_queue.task_done()                          
            

    def write_to_log(self) -> bool:
        try:

            return write_json(self.log, self.parent_directory)
        except Exception as e:
            self.output(traceback.format_exc(e), error=True)
            return False    

    def write_to_csv(self, image:cam_image.Cam_Image) -> bool:
        try:
            
            with open(self.csv_file_path, "a") as csv_file:
                if csv_file.tell() == 0:
                    csv_file.write(",".join(list(image.info.keys())))
                csv_file.write(",".join(list(image.info.values())))
        
        except:
            pass
    
    def update_session_list(self):
        session_list = {}
        if self.session_list_file.exists():
            try:
                with open(self.session_list_file, "r") as session_list_file:
                    session_list = json.load(session_list_file)
            except:
                session_list = {}
        
        session_list[self.name] = self.details
        
        with open(self.session_list_file, "w") as session_list_file:
            json.dump(session_list, ensure_ascii=False, indent=5)
    
    
    def output(self, output:str|list) -> bool:
        try:

            with open(self.parent_directory / f"{self.name.replace(' ', '_')}" / "output.txt", "a") as session_output_file:
                session_output_file.write(output + '\n')
                        
            return True
        except Exception as e:
            traceback.print_exc(e)
            return False
    
    def run_and_log(self, function):
        try:
            with open(self.parent_directory / f"{self.name.replace(' ', '_')}" / "output.txt", "a") as session_output_file:
                with redirect_output(session_output_file):
                    return function()
                        
        except Exception as e:
            traceback.print_exc(e)
            return False
        
    def print_info(self):
        print(" Session Info")
        print("             Name:", self.name)
        print("       Start Time:", self.time_string())
        print(f"    Data location: {self.parent_directory}")
        print("         Latitude:", self.coords[0])
        print("        Longitude:", self.coords[1])
        print(" Number of images:", len(self.log['images']))              
         
             
def write_json(log:dict, filepath:Path) -> bool:
    try:
        with open(filepath, "w") as session_log_file:
            json.dump(log, session_log_file, indent=5, ensure_ascii=False)
                        
        return True
    
    except Exception as e:
        traceback.print_exc(e)
        return False                    
    
    
def confirm(message:str, default:bool=None) -> bool:
        if default is None:
            options = "y/n"
        else:
            if default:
                options = "[y]/n"
            elif not default:
                options = "y/[n]"
        response = input(f"{message} [{options}]:").lower()
        
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
        
def get_coords() -> tuple[float]:
    
    def get_input(message:str, max:float, min:float=None) -> float:
        coords_string = input(message)
        if coords_string == "":
            return None
        coord = validate_input(coords_string, max)
        if coord is not None:
            return coord
        else: 
            return get_input(message, max, min)
    
    def validate_input(value:str, max:float, min:float=None):
        if min is None:
            min = max*-1
        
        try:
            
            value = float(value)
            if min <= float(value) <= max:
                return float(value)
            else:
                print("Coordinate out of range")
                print(f"Enter a value between {min} and {max}.")
                print("Use positive coordinates for North and East, negative for South and West.")
                return None
        except ValueError:
            print("Not a valid decimal coordinate.")
            print("Use positive coordinates for North and East, negative for South and West.")
            print("Do not enter compass direction.")
            print("Leave empty to use blank coordinates")
            return None
            
    
    if confirm("Enter coords?"):
        latitude, longitude = (None, None)
        latitude = get_input("Decimal Latitude: ", max=90)
        if latitude is not None:
            longitude = get_input("Decimal Longitude: ", max=180)
            
        return (latitude, longitude)
    return (None, None)

    
def get_start_time():
    if confirm("Enter start time?"):
        time_string = input("Enter start time in format 'YYYY-MM-DD HH:MM:SS': ")
        if time_string == "":
            return None
        try:
            start_time = datetime.strptime(time_string, PRETTY_FORMAT)
            print("Start time set to: ",datetime.strftime(start_time,PRETTY_FORMAT))
            return start_time
        except Exception as e:
            print("Invalid format. Leave blank to use current time")
            return get_start_time()
    
    return None

def get_directory():
    print(f"By default session data will be saved at '{str(DATA_DIR / 'sessions')}'.")
    
    new_directory = input("Hit Return to use default, or enter custom directory path: ")
    if new_directory == "":
        return None
    else:
        try:
            if Path(new_directory).exists():
                return new_directory
            else: 
                if confirm("Directory does not exist. Create directory?"):
                    try:
                        Path(new_directory).mkdir(parents=True, exist_ok=True)
                        return new_directory
                    except:
                        print(f"Unable to create directory '{new_directory}'")
                        get_directory()
                else:
                    return None
            
        except Exception as e:
            print("Error selecting directory")
            get_directory()
            return 
 
def validate_name(name) -> bool:
    if name is None:
        return False
    
    for char in "<>:/\\;|?*[]\"'.":
        if char in name:
            print("Entered name not valid. Name must not contain any of the following: <>:/\\;|?*[]\"'. ")
            return False
    return True

def get_valid_name(name:str|None=None) -> str:
    
    if validate_name(name):
        return name
        

    name = input("Enter Name for Session or leave blank for default: ")
    
    if name == "":
        return None
    
    else:
        return get_valid_name(name)

                     
    
        
def start_session(name:str|None=None, coords:tuple[float|None] = (None,None), start_time:datetime|None = None, directory:str|None=None):
    
    name = get_valid_name(name)
            
    if coords == (None, None):
        coords = get_coords()
        
    if start_time is None:
        start_time = get_start_time()
        
    if directory is None:
        directory = get_directory()
        

    session = Session(name, coords, start_time, directory)
    
    print(f"Created Session: '{session.name}'")
    session.print_info()
    
    return session 

def from_file(path:str|Path) -> Session:
    """Open Session:
        Open a session from a log file

    Args:
        log_file (str): path to log session

    Returns:
        Session: A session object with details matching those in log file
    """    
    try:
        log_file = Path(path) / "log.json"
        if not log_file.exists():
            print("Session does not exist")
            return None
        
        session_dict = {}
        with open(log_file, mode="r") as file:
            session_dict = json.load(file)
        
        name = session_dict["session"]
        start_time = datetime.strptime(session_dict["start_time"], "%Y-%m-%d %H:%M:%S")
        coord_str = session_dict["coords"]
        coords = []
        for i in coord_str.split(", "):
            if i == "None":
                coords.append(None)
            else:
                coords.append(float(i))
                
        coords = tuple(coords)
        
        path = session_dict["path"]
        session = Session(name=name, start_time=start_time, coords=coords, directory=path, images=session_dict['images'])
        
        print("Opened session:")
        session.print_info()
        
        return session
    
    
    except Exception as e:
        traceback.print_exc(e)
        return None
    
def create_sessions_list(directory:str|Path):
    if isinstance(directory, str):
        directory = Path(directory)
    list_file = directory / "session_list.json"
    
    if list_file.exists():
        return True

    #TODO: check for existing sessions in subfolders
    def create_file():

        with open(list_file, "w") as file:
            file.write("{}")
        return True
 
    

    return create_file()

    