
import time
import traceback
from pathlib import Path
import numpy as np
import json

CAPTURE_START = "capture_start"
CAPTURE_END="capture_end"
ACCEPTED_PARAMS={"name":str, "initial_delay_time_secs":(float,int), "number_limit":(float,int),
                 "time_limit_secs":(float,int), "repeat":(float, int), "interval_mode":str,
                 "interval_secs":(float,int), "integration_time_secs":(float,int),
                 "loop_integration_time":bool, "gain":(float,int), "loop_gain":bool,
                 "min_tick_length_secs":(float,int), "all_combinations":bool}

class Routine:
    
    def placeholder_capture(integration_time, gain, auto):
        int_string = f"{round(integration_time, 6)}s"
        if integration_time == 0 or auto:
            int_string = "Auto-adjust"
        
        
        print(f"Exposure time: {int_string} | gain: {gain}")
        time.sleep(integration_time)
        print("Capture Complete")
        return None

    def __init__(self, name,
                 initial_delay_time_secs:float=0, 
                 number_limit:int|float=5000,
                 time_limit_secs:float=345600,
                 repeat:int|float = 1,
                 interval_mode:str=CAPTURE_END, 
                 interval_time_secs:float=0,
                 integration_time_secs:float|list=0, 
                 loop_integration_time:bool=False,
                 gain:float|list=1, 
                 loop_gain:bool=False,
                 all_combinations:bool=False,
                 min_tick_length_secs:float=0.01,
                 capture_function:callable=placeholder_capture) -> None:

        
        
        self.name = name
        
        self.initial_delay=initial_delay_time_secs
        self.number_limit = min(int(number_limit), 5000) #max images is 5000
        
        self.time_limit_secs = min(time_limit_secs, 345600) #maximum time is 96 hours 
        self.repeat = int(repeat)
        
        settings = Routine._create_settings_matrix(integration_times=integration_time_secs,
                                                       gains=gain,
                                                       all_combinations=all_combinations,
                                                       number_limit=self.number_limit,
                                                       loop_gain=loop_gain,
                                                       loop_integration_time=loop_integration_time)
        
        if self.repeat == 0:
            self.repeat = int(self.number_limit // np.size(settings[0,:]))

        
        settings = np.tile(settings, self.repeat)

        
        self.int_times = settings[0,:]
        self.gains = settings[1,:]
        

        self.repeat = int(repeat)
                
        if interval_mode.lower() not in [CAPTURE_START, CAPTURE_END]:
            print("Interval mode not recognised, setting to default: CAPTURE_START ")
            interval_mode = CAPTURE_START
        self.interval_mode=interval_mode
        
        self.interval_secs = interval_time_secs
        
        self.tick_length = min(min_tick_length_secs, 0.001)
        #Variables for running
        self.capture_function = capture_function
        self.start_time = None
        self.next_capture = None
        self.image_count = 0
        self.complete = False
        self.last_time_printed=0
        
    def to_string(self, print_string:bool=False):
        string = ""
        string += f"Routine: {self.name}"
        string += f"\nInitial delay: {self.initial_delay}s"
        string += f"\nNumber Limit: {self.number_limit}"
        string += f"\nTime Limit: {self.time_limit_secs}s"
        string += f"\nInterval: {self.interval_secs}s"
        string += f"\nInterval Mode: {self.interval_mode}"
        string += f"\nRepeat: {self.repeat}"
        string += f"\nIntegration_times (s): { (str(self.int_times[:7]).strip(']') + '...]') if len(str(self.int_times)) > 10 else str(self.int_times)}"
        string += f"\nGain settings: { (str(self.gains[:7]).strip(']') + '...]') if len(str(self.gains)) > 10 else str(self.gains)}"
        if self.tick_length != 0.01:
            string += f"\nTick length: {self.tick_length}"
        string+="\n"
        if print_string:
            print(string)
        return string
        
    def capture_image(self, integration_time, gain):

        auto = False
        int_string = str(integration_time)+'s'
        if integration_time == 0:
            auto = True
            int_string = "Auto"
        
        print(f"{round(time.time()-self.start_time, 2)}s ==> Capturing Img #{self.image_count+1} ~ I:{int_string} | G: {gain}dB")
        image = self.capture_function(integration_time, gain, auto)
        self.image_count += 1
        return image
    
    def set_next_capture_time(self):

        if self.interval_mode == CAPTURE_END:
            self.next_capture = time.time()+self.interval_secs
        else:
            self.next_capture = self.next_capture + self.interval_secs
        
    def tick(self):
        captured_image = None
        string = ""
        
        def tick_outcome(value:bool=True, return_string:str=""):
            return({"complete": value,
                    "image": captured_image ,
                    "image_count": self.image_count,
                    "string": return_string})
        
        if self.start_time is None:
            self.start_time = time.time()
            print("Starting routine ", self.name)
            self.next_capture =  self.start_time + self.initial_delay
            
        now = time.time()
        run_time = now-self.start_time
        

        if self.number_limit is not None:
            self.complete = self.image_count >= self.number_limit
        
         
        if self.time_limit_secs is not None:
            if not self.complete:
                self.complete = run_time >= self.time_limit_secs
            
        if not self.complete:
            self.complete = self.image_count >= len(self.int_times)
              
        if self.complete:
            print("Routine Complete")
            return tick_outcome(True)  
        
        
          
            
        if now > self.next_capture:
            captured_image = self.capture_image(self.int_times[self.image_count], self.gains[self.image_count])
            self.set_next_capture_time()
        
        tick_remaining = self.tick_length-(time.time()-now)
        if tick_remaining > 0:
            time.sleep(tick_remaining)
         
        return tick_outcome(False)
    

    
    def _create_settings_matrix(integration_times, gains, all_combinations, number_limit, loop_integration_time, loop_gain):
        integration_times = np.array(integration_times)
        gains = np.array(gains)
        settings = None
        
        # if all_combinations is TRUE, create a setting array of all possible unique combinations of gain and
        # integration times 
        if all_combinations:
            #reduce integration times and gain to just unique values
            integration_times =  integration_times[np.sort(np.unique(integration_times, return_index=True)[1])]
            gains = gains[np.sort(np.unique(gains, return_index=True)[1])]
            
            settings = np.array(np.meshgrid(integration_times, gains)).reshape(2,-1)
        
            return settings
        

        #If either gain or integration time are a single value, extend them out into an array
        # as long as the other, or as long as the number limit if both are single value
        if integration_times.size == 1:
            if gains.size > 1:
                integration_times = np.full(gains.size, integration_times)
            else:
                integration_times = np.full(number_limit, integration_times)

        if gains.size == 1:
            gains = np.full(integration_times.size, gains)

        
        #if gain or integ time is longer than the other, cut it down to the shorter length
        # or, if loop is TRUE for the shorter, extend it to the longer length by repeating it
        if gains.size < integration_times.size:
            if loop_gain:
                gains.resize(integration_times.size)
            else:
                integration_times = integration_times[:gains.size]
        elif gains.size > integration_times.size:
            if loop_integration_time:
                integration_times.resize(gains.size)
            else: 
                gains = gains[:integration_times.size]     
        
        #Stack integration times and gain arrays in the shape:
        #                           0  1  2  3
        # integration times --> 0 [[1, 2, 3, 4],
        #       gain values --> 1 [5, 6, 7, 8]]
        
        # i.e to access a gain value for a given index, use settings[1,[index]]
        # and for integration times, use settings[0,[index]]
        settings:np.ndarray = np.vstack([integration_times, gains])
        
        
        return settings


    
def convert(val:str)-> float|str|bool: #try to convert value to the correct datatype
    val = val.strip()
    try:    #try to convert to float, leave as string if not
        val = float(val)
        return val
    except Exception as e:
        pass
    if val.lower() in ["true", "t", "yes", "y"]: #convert to boolean if possible
        val = True
    elif val.lower() in ["false", "f", "no", "n"]:
        val = False
    
    return val
    
def parse_value(value:str) -> str|list|float|bool:
    value = value.strip()
    if value.startswith("["):
        if not value.endswith("]"):
            return None
        list_type = None
        val_list = []
        for item in value.strip(" []").split(","):
            item = item.strip()
            item = convert(item)
            if list_type is None: #for first item, set type of list to what that item is
                list_type = type(item)
            else:
                if type(item) != list_type: #check the type of item matches the list 
                    return None
            val_list.append(item)
        return val_list
    

    
    value = convert(value)
    

    return value            
        
                
        
    
def parse_line(line:str) -> dict:
        try:
            line = line.strip()
            if line.startswith("#") or line == "" or ":" not in line:
                return None
            line = line.split(" #", 1)[0] #remove inline comments
            parameter, value = line.split(":")
            parameter = parameter.strip().lower()
            value = value.strip()
            parameter = parameter.replace(" ", "_")
            
            value = parse_value(value)
            return (parameter, value)
        except Exception as e:
            traceback.print_exc(e)
            return None
        
def convert_to_seconds(value:int|float, unit:str)->float:
    unit = unit.lower()
    multiplier = None
    match unit:
        case h if h in ["hours", "hour", "hrs", "hr", "hs", "h"]:
            multiplier = 60*60
        case m if m in ["minutes", "minute", "mins", "min", "m"]:
            multiplier = 60
        case s if s in ["seconds", "second", "sec", "secs", "s"]:
            multiplier = 1
        case ms if ms in ["milliseconds", "millisecond", "ms"]:
            multiplier = 1/1000
        case us if us in ["microseconds", "microsecond", "us"]:
            multiplier = (1/1000)/1000
        case _:
            multiplier = 1
    
    try:
        result = [item*multiplier for item in value]
    except TypeError:
        result =value*multiplier
    return result

def from_dict(params:dict, capture_function:callable=Routine.placeholder_capture) -> Routine:
    
    valid_params = {}

    units = {"default_time_unit":"s",
             "time_limit_unit":None, 
             "initial_delay_time_unit":None,
             "interval_time_unit":None,
             "integration_time_unit":None,
             "min_tick_length_unit":None}
    
    times = {"time_limit":None,
             "initial_delay_time":None,
             "interval_time":None,
             "integration_time":None,
             "min_tick_length":None}
    for key, value in params.items():
        
        valid=key in ACCEPTED_PARAMS and isinstance(value, ACCEPTED_PARAMS[key])
        if valid:
            if key in valid_params: #If the parameter is already set, notify and update
                #Create short string representing value to print if value is longer than 10 chars
                val_string =  (str(value[:7]) + '...') if len(str[value]) > 10 else str[value]
                valid_params[key] = value
                print(val_string)
            else:
                valid_params.update([(key, value)])
            continue
        
        #Find parameters for setting times and time units
        match key: 
            case unit_param if unit_param in units:
                units[key] = value
            case time_param if time_param in times:
                times[key] = value
    

    for param, value in times.items(): #convert any time parameters to seconds
        if value is not None:          #by getting the unit it is currently in
            unit = units[f"{param}_unit"] #and multiplying to convert
            if unit is None:
                unit = units["default_time_unit"]
            
            time_in_secs = convert_to_seconds(value, unit)
            valid_params.update([(f"{param}_secs", time_in_secs)])
            
    return Routine(capture_function=capture_function, **valid_params)
    
        
        
def from_file(file_path:str|Path, capture_function:callable=Routine.placeholder_capture) -> Routine:
        try:
            
            lines = []
            with open(file_path, mode="r") as file:
                   lines = file.readlines()  
                   
            
            params = {}
            for line in lines:
                parsed_line = parse_line(line)
                if parsed_line is not None:
                    params.update([parsed_line])
                
            return from_dict(params, capture_function=capture_function)
                
        except Exception as e:
            print(f"Problem opening routine file at {file_path}")
            print(traceback.format_exc(e))
            #traceback.print_exc(e)
        
        

