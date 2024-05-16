from harvesters.core import Harvester, ParameterSet, ParameterKey, ImageAcquirer, NodeMap, Buffer
import os
import numpy as np
from datetime import datetime, timedelta
import traceback
from cam_image import Cam_Image
from time import sleep
import math
import sys
import threading

from eprint import eprint
PRODUCER_PATH = os.environ.get('PRODUCER_PATH')
PRODUCER_PATH = "/opt/ids-peak-with-ueyetl_2.7.1.0-16417_arm64/lib/ids/cti/ids_u3vgentl.cti"

#Return Types
CAM_IMAGE = "cam_image"
"""cam_image.Cam_Image object"""
NDARRAY = "nd_array"
"""numpy.ndarray Object"""

#Pixel Formats

MONO8 = "Mono8"
""" 8-bit monochrome pixel format """
RGB8 = "RGB8"
""" 8-bit RGB pixel format """
BAYER_RG8 = "BayerRG8"
""" 8-bit Bayer RG pixel format """

#Acquisition Modes
SINGLE_FRAME = "SingleFrame"
""" Single Frame Acquisition Mode """
MULTI_FRAME = "MultiFrame"
""" Multi Frame Acquisition Mode """
CONTINUOUS = "Continuous"
""" Continuous Acquisition Mode """

#Sensor Operation Modes
DEFAULT = "Default"
""" Default Sensor Mode """
LONG_EXPOSURE = "LongExposure"
""" Long Exposure Sensor Mode """


#Time Units
US = "microseconds"
""" Microseconds """
MICROSECONDS = "microseconds"
""" Microseconds """

S = "seconds"
""" Seconds """
SECONDS = "seconds"
""" Seconds """

MS = "milliseconds"
""" Milliseconds """
MILLISECONDS = "milliseconds"
""" Milliseconds """

NS = "nanoseconds"
""" Nanoseconds """
NANOSECONDS = "nanoseconds"
""" Nanoseconds """

class Camera:

    
    def connect(self):
        try:
            self.harvester.update()
            
            # Create an image acquirer with auto chunk data update enabled
            self.acquisition_params = ParameterSet()
            self.acquisition_params.add(ParameterKey.ENABLE_AUTO_CHUNK_DATA_UPDATE, True)
            self.device:ImageAcquirer = self.harvester.create(config=self.acquisition_params)
            
            self.nodemap:NodeMap = self.device.remote_device.node_map
            self.data_stream = self.device.data_streams[0]
            self.ds_nodemap: NodeMap= self.data_stream.node_map
            #Set Buffer Handling Mode to Newest Only
            self.ds_nodemap.StreamBufferHandlingMode.set_value("NewestOnly")
            
            #Reset device timestamp to zero
            self.nodemap.TimestampReset.execute()
            while not self.nodemap.TimestampReset.is_done():
                sleep(0.1)
            self.start_time = datetime.now()

        except Exception as e:
            traceback.print_exception(e)


    def __init__(self) -> None:
        
        self.harvester = Harvester() 
        
        # Add producer file path
        self.harvester.add_file(PRODUCER_PATH)


        self.connect()
        self.start_time = datetime.now()

        self.cap_thread:threading.Thread = None
        #Set Pixel Format to BayerRG8 if available, else set to Mono8
        if BAYER_RG8 in self._valid_pixel_formats():
            self.nodemap.PixelFormat.set_value(BAYER_RG8)
        else:
            self.nodemap.PixelFormat.set_value(MONO8)
        
        # Activate chunk mode and enable pixelformat and exposure time chunks so the device passes this data along with the image
        chunks = ["Timestamp", "ExposureTime", "Width", "Height", "PixelFormat", "Gain"]
        self.activate_chunks(chunks)

    
    def activate_chunks(self, chunks:list[str]=["Timestamp", "ExposureTime", "Width", "Height", "PixelFormat", "Gain"]):  
        self.nodemap.ChunkModeActive.set_value("False")
        for entry in self.nodemap.ChunkSelector._get_symbolics():
            if entry in chunks:
                self.nodemap.ChunkSelector.set_value(entry)
                self.nodemap.ChunkEnable.set_value("True")
        self.nodemap.ChunkModeActive.set_value("True")
        
        
    def start_acquisition(self, mode:str="Continuous"):
        self.activate_chunks()
        if self.device.is_acquiring():
            return

        self.nodemap.AcquisitionMode.set_value(mode)
        self.device.start()

    @property
    def connected(self):
        return self.device.is_valid()
    
    @property
    def acquiring(self):
        return self.device.is_acquiring()
                
    def capture_image(self, return_type:str=CAM_IMAGE, target_integration_time_us:int=None):
        try:
            if not self.device.is_acquiring():
                raise Exception("Device is not acquiring")
            

            image_array = None
            
            buffer:Buffer = None
            
            correct_integration_attempts = 0
            fetch_attempts = 0
            integration_time_us = None
            while buffer is None:
                
                try:
                    buffer:Buffer = self.device.fetch()
                    #buffer.update_chunk_data()
                    integration_time_us = self.nodemap.ChunkExposureTime.value
                    
                    if target_integration_time_us is not None:
                        if abs(integration_time_us - target_integration_time_us) > target_integration_time_us/10:
                            buffer.queue()
                            buffer = None
                    else:
                        if correct_integration_attempts == self.data_stream.num_announced:
                            break
                        buffer.queue()
                        buffer=None
                        correct_integration_attempts += 1
            
                except Exception as e:
                    traceback.print_exception(e, file=sys.stderr)
                    fetch_attempts +=1
                    if fetch_attempts > 10:
                        raise Exception("Failed to fetch buffer after 10 attempts")

            clock_timestamp = buffer.timestamp_ns/(10**9)
            component = buffer.payload.components[0]
            image = component.data
            
            image_array = image.reshape(component.height, component.width).copy()

            if return_type == NDARRAY:
                buffer.queue()
                return image_array

            format = component.data_format

            
            buffer.queue()

            timestamp = self.start_time + timedelta(seconds = clock_timestamp)
            
            temperature = self.nodemap.DeviceTemperature.value

            return Cam_Image(image_array, 
                             format=format,
                             timestamp = timestamp, 
                             integration_time_us = integration_time_us,
                             gain = 1, 
                             aperture=1,
                             cam_temp=temperature)
        except Exception as e:
            traceback.print_exception(e)
            return None    
    
    
    def start_continuous_capture(self, callback,  callback_args=[], auto:bool=False, integration_time_us=None, gain:float=None, callback_as_thread:bool=True):
        self.cap_thread = threading.Thread(target=self._continous_capture_thread, args = [callback, callback_args, auto, integration_time_us, gain, callback_as_thread], daemon=True)
        self.cap_thread.daemon = True
        self.cap_thread.start()
        
    
    def _continous_capture_thread(self, callback, callback_args=[], auto:bool=False, integration_time_us=None, gain:float=None, callback_as_thread:bool=False):
        self.stop_acquisition()
        auto_value = self.nodemap.ExposureAuto.value
        sensor_mode = self.nodemap.UserSetSelector.value
        
        self.change_sensor_mode(DEFAULT)
        self.nodemap.AcquisitionMode.set_value(CONTINUOUS)
        auto_value = self.nodemap.ExposureAuto.value
        if integration_time_us is not None and auto_value == "Off":
            self.integration_time(integration_time_us)
        
        self.stop_capture = False
        if auto:
            self.nodemap.ExposureAuto.set_value(CONTINUOUS)
        callback_thread:threading.Thread = None
        self.start_acquisition()
        while not self.stop_capture:
            try:
                if not self.acquiring:
                    break
                with self.device.fetch() as buffer:
                    component = buffer.payload.components[0]
                    image_array = component.data.copy()
                    shape = np.array((component.height, component.width)).copy()
                    integration_time_us = self.nodemap.ChunkExposureTime.value
                    if callback_as_thread:
                        callback_thread = threading.Thread(target=callback, args=[image_array, integration_time_us, shape, *callback_args], daemon=True)
                        callback_thread.daemon = True
                        callback_thread.start()
                    else:
                        callback(image_array, integration_time_us, callback_args)
            except Exception as e:
                traceback.print_exception(e)
                self.stop_capture = True
                break

        self.stop_acquisition()
        self.nodemap.ExposureAuto.set_value(auto_value)
        self.change_sensor_mode(sensor_mode)
            
            
    def stop_continous_capture(self):
        self.stop_capture = True
        if self.cap_thread is not None:
            self.cap_thread.join()
    
    def _get_integration_time_us(self):
        """
        Get the integration time in microseconds.

        Returns:
            float: The integration time in microseconds.
        """
        return self.nodemap.ExposureTime.value
    
    def set_auto_params(self, target:int, tolerance:float, percentile:float, min_int=0, max_int=None, time_unit:str=MICROSECONDS):
        
        if min_int != 0 or max_int is not None:
            self.nodemap.BrightnessAutoExposureTimeLimitMode.set_value("On")
        min_int = convert_time(min_int, time_unit, MICROSECONDS)
        
        
        int_min_poss, int_max_poss = self._get_integration_min_max()
        if max_int is None:
            max_int = int_max_poss
        else:
            max_int = convert_time(max_int, time_unit, MICROSECONDS)
            
        self.nodemap.BrightnessAutoExposureTimeMin.set_value(max(min_int, int_min_poss))
        self.nodemap.BrightnessAutoExposureTimeMax.set_value(min(max_int, int_max_poss))
        
        
        self.nodemap.BrightnessAutoTarget.set_value(target)
        self.nodemap.BrightnessAutoTargetTolerance.set_value(tolerance)

        self.nodemap.BrightnessAutoPercentile.set_value(percentile)
        
    
    @property
    def temp(self):
        return self.nodemap.DeviceTemperature.value
    
        
    @property
    def temperature(self):
        return self.nodemap.DeviceTemperature.value
    
    
    @property
    def integration_time_microseconds(self):
        return self._get_integration_time_us()
    
    @property
    def integration_time_seconds(self):
        return convert_time(self._get_integration_time_us(), MICROSECONDS, SECONDS)

    def _get_integration_min_max(self, time_unit:str=MICROSECONDS)-> tuple:
        """
        Get the minimum and maximum integration time for the device.

        Args:
            time_unit (str): The unit of time to convert the integration time to. Default is MICROSECONDS.

        Returns:
            tuple: A tuple containing the minimum and maximum integration time in the specified time unit.
        """
        min_time = convert_time(self.nodemap.ExposureTime.min, MICROSECONDS, time_unit)
        max_time = convert_time(self.nodemap.ExposureTime.max, MICROSECONDS, time_unit)
        return min_time, max_time
    
    def integration_time(self, time:float=None, time_unit:str=MICROSECONDS):
        try:
            
            if time is None:
                return convert_time(self._get_integration_time_us(), MICROSECONDS, time_unit)
            
            if time < 0:
                raise ValueError("Integration time must be positive")
            
            if self.nodemap.ExposureAuto.value != "Off":
                raise ValueError("Auto Exposure is enabled")
            
            #Get current settings

            acquisition_state = self.device.is_acquiring()
            
            time_us = convert_time(time, time_unit, MICROSECONDS)

            min_time, max_time = self._get_integration_min_max(time_unit=MICROSECONDS)   
            sensor_mode = self.nodemap.SensorOperationMode.value
            
            if time_us < min_time:
                if sensor_mode == LONG_EXPOSURE:
                    self.stop_acquisition()
                    self.change_sensor_mode(DEFAULT)
            
            if time_us > max_time:
                if sensor_mode == DEFAULT:
                    self.stop_acquisition()
                    self.change_sensor_mode(LONG_EXPOSURE)
            
            min_time, max_time = self._get_integration_min_max(time_unit=MICROSECONDS)   
            
            time_us = max(min_time, min(max_time, time_us))
            
            self.nodemap.ExposureTime.set_value(time_us)
            

            if acquisition_state:
                self.device.start()

            return convert_time(self.nodemap.ExposureTime.value, MICROSECONDS, time_unit)
        except Exception as e:
            print("Problem setting exposure time", file=sys.stderr)
            traceback.print_exception(e, file=sys.stderr)
            return None
        
    def change_sensor_mode(self, mode:str=DEFAULT):
        if self.nodemap.UserSetSelector.value == mode:
            return
        
        acquisition_state = self.device.is_acquiring()
        acquisition_mode = self.nodemap.AcquisitionMode.value
        current_pixel_format = self.nodemap.PixelFormat.value
        current_gain = self.nodemap.Gain.value
        current_buffer_handling_mode = self.ds_nodemap.StreamBufferHandlingMode.value
        
        self.stop_acquisition()
            
        if mode not in [DEFAULT, LONG_EXPOSURE, "UserSet0", "UserSet1"]:
            raise ValueError("Invalid Sensor Mode")
        self.nodemap.UserSetSelector.set_value(mode)
        self.nodemap.UserSetLoad.execute()
        
        self.nodemap.PixelFormat.set_value(current_pixel_format)
        self.nodemap.Gain.set_value(current_gain)
        self.ds_nodemap.StreamBufferHandlingMode.set_value(current_buffer_handling_mode)
        self.nodemap.AcquisitionMode.set_value(acquisition_mode)
        
        if acquisition_state:
            self.start_acquisition()
    
    def _get_gain_min_max(self):
        return self.nodemap.Gain.min, self.nodemap.Gain.max
    
    def gain(self, gain:float=None):
        try:
            if gain is None:
                return self.nodemap.Gain.value
            if gain < 0:
                raise ValueError("Gain must be positive")
            
            gain_min, gain_max = self._get_gain_min_max()
            gain = max(gain_min, min(gain_max, gain))
            
            self.nodemap.Gain.set_value(gain)
            return self.nodemap.Gain.value
        except Exception as e:
            print("Problem setting gain")
            traceback.print_exception(e)
            return None
    
    def set_to_manual(self, setting:list[str]=["ExposureTime", "Gain", "WhiteBalance", "ColorCorrection"]):
        if "ExposureTime" in setting:
            try:
                self.nodemap.ExposureAuto.set_value("Off")
            except:
                pass
        if "Gain" in setting:
            try:
                self.nodemap.GainAuto.set_value("Off")
            except:
                pass
        if "WhiteBalance" in setting:
            try:
                self.nodemap.BalanceWhiteAuto.set_value("Off")
            except:
                pass
        if "ColorCorrection" in setting:
            try:
                self.nodemap.ColorTransformationAuto.set_value("Off")
            except:
                pass
        
    def stop_acquisition(self):
        if self.device.is_acquiring():
            self.device.stop()
    
    def disconnect(self):
        self.stop_acquisition()
        self.device.destroy()
        self.harvester.reset()
        
    def print_settings(self):
        print("User Set: ", self.nodemap.UserSetSelector.value)
        print("Exposure Time: ", self.nodemap.ExposureTime.value/(10**6), "S")
        print("Gain: ",self.nodemap.Gain.value)
        
        print("ExposureMode: ",self.nodemap.ExposureMode.value)
        print("ExposureAuto: ",self.nodemap.ExposureAuto.value)
        print("Brightness Auto Exposure Time Limit: ",self.nodemap.BrightnessAutoExposureTimeMax.value/(10**6), "S")
        print("GainAuto: ",self.nodemap.GainAuto.value)
        print("Sensor Op Mode: ",self.nodemap.SensorOperationMode.value)
        print("Camera Temp: ", self.nodemap.DeviceTemperature.value)
        
        print("Min Exposure Time: ", self.nodemap.ExposureTime.min/(10**6), "S")
        print("Max Exposure Time: ", self.nodemap.ExposureTime.max/(10**6), "S")


    def save_set(self, number):
        self.nodemap.UserSetSelector.set_value(f"UserSet{number}")
        self.nodemap.UserSetSave.execute()

    def load_set(self, set:int|str):
        try:
            pixel_format = self.nodemap.PixelFormat.value
            set = int(set)
            if set in [0,1]:
                self.nodemap.UserSetSelector.set_value(f"UserSet{set}")
                self.nodemap.UserSetLoad.execute()
                self.nodemap.AcquisitionMode.set_value("SingleFrame")
                print("Loading set", set)
                return
        except ValueError:
            if set in self.nodemap.UserSetSelector._get_symbolics():
                self.nodemap.UserSetSelector.set_value(set)
                self.nodemap.UserSetLoad.execute()
                self.nodemap.AcquisitionMode.set_value("SingleFrame")
                print("Loading set", set)
                return
            
        except Exception as e:
            traceback.print_exception(e)
        
        finally:
            self.set_pixel_format(pixel_format)
            print(f"Invalid User Set '{set}'")
            
    def _valid_pixel_formats(self):
        return self.nodemap.PixelFormat._get_symbolics()
        
    def _node_list(self, nodemap=None):
        if nodemap is None:
            nodemap = self.nodemap
            
        node_list = []
        for item in nodemap._get_nodes():
            try:
                node = item._get_node()
                node_tuple = (node._get_display_name(), item.to_string())
            except:
                node_tuple = (node._get_display_name(), None)
            finally:
                node_list.append(node_tuple)
        
        return node_list
    
    def _query_node_list(self, name, nodemap=None):
        for node, value in self._node_list(nodemap=nodemap):
            if name in node:
                try:
                    print(f"{node}: {value}")
                    pass
                except:
                    print(f"{node}: {value}")
                    pass
       
       
def convert_time(value: float|int, input_unit: str, target_unit: str) -> float|int:
    """
    Converts a time value from one unit to another.

    Args:
        value (float|int): The time value to be converted.
        input_unit (str): The unit of the input time value.
        target_unit (str): The unit to which the time value should be converted.

    Returns:
        float|int: The converted time value.

    Raises:
        None

    Examples:
        >>> convert_time(1000, "milliseconds", "seconds")
        1.0
        >>> convert_time(1, "seconds", "milliseconds")
        1000.0
    """
    if input_unit == target_unit:
        return value
    unit_dict = {"seconds": 1, "milliseconds": 10**3, "microseconds": 10**6, "nanoseconds": 10**9}
    return value * unit_dict[target_unit] / unit_dict[input_unit]


def calculate_new_integration_time(current_integration_time, saturation_fraction:float, target_fraction:float=0.01):
    
    overexposed_difference = saturation_fraction - target_fraction #Calculate how far the image is from correct saturation level
    #Calculate adjustment factor. The current integration time will be multiplied by this to get the new integration time guess.
    #The factor is limited to between 20 and 0.01 (as sometimes small values can lead to crazy numbers)
    
    #The adjustment scales with the ralationship between the size of the saturation error and the target saturation fraction
    #If the difference is large, the adjustment is large, and vice versa. This is fairly quick but could probably be optimised (Maybe with a PID type control?)

    adjustment_factor = min(10, max(0.1, 1 - (overexposed_difference)/target_fraction ))
    

    #Calculate the new guess for a good integration time
    new_integration_time  = current_integration_time*adjustment_factor
        
    return new_integration_time

def calculate_new_integration_time_pid(current_integration_time, saturation_fraction:float, integral_error:float, target_fraction:float=0.01, Kp=1.0, Ki=0.1):
# Calculate how far the image is from correct saturation level
    # Take the logarithm of the saturation fraction to linearize the relationship
    overexposed_difference = math.log(saturation_fraction) - math.log(target_fraction)

    # Calculate proportional term
    proportional_error = overexposed_difference / math.log(target_fraction)

    # Update integral term
    integral_error += overexposed_difference

    # Calculate adjustment factor using PI controller
    adjustment_factor = Kp * proportional_error + Ki * integral_error

    # Calculate the new guess for a good integration time
    new_integration_time  = current_integration_time * adjustment_factor

    return new_integration_time, integral_error
     
        
if __name__ == "__main__":
    c = Camera()
    c._query_node_list("Flush")
    image = c.capture_image(auto=True)
    #c._query_node_list("AutoExposure")
    