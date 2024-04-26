from contextlib import contextmanager
import sys,os
import warnings


@contextmanager
def suppress_stdout():
    """Hides error messages when importing ids modules
    """    
    with open(os.devnull, "w") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:  
            yield
        finally:
            sys.stdout = old_stdout
            
with suppress_stdout():
    from ids_peak import ids_peak
    from ids_peak_ipl import ids_peak_ipl
    from ids_peak import ids_peak_ipl_extension
    #from ids_peak_afl import ids_peak_afl_extension
    import traceback #Module for finding Exception causes more easily
    from datetime import datetime
    import numpy as np
    import ctypes

    import cam_image
    
class Resources:
    #Pixel Formats
    MONO8 = ids_peak_ipl.PixelFormatName_Mono8
    MONO10 = ids_peak_ipl.PixelFormatName_Mono10
    MONO12 = ids_peak_ipl.PixelFormatName_Mono12
    RGB8 = ids_peak_ipl.PixelFormatName_RGB8
    BGR8 = ids_peak_ipl.PixelFormatName_BGR8


    BAYER_RG8 = ids_peak_ipl.PixelFormatName_BayerRG8
    BAYER_RG12 = ids_peak_ipl.PixelFormatName_BayerRG12
    BAYER_BG8 = ids_peak_ipl.PixelFormatName_BayerBG8
    BAYER_BG12 = ids_peak_ipl.PixelFormatName_BayerBG12
    BAYER_GR8 = ids_peak_ipl.PixelFormatName_BayerGR8
    BAYER_GR12 = ids_peak_ipl.PixelFormatName_BayerGR12
    BAYER_GB8 = ids_peak_ipl.PixelFormatName_BayerGB8
    BAYER_GB12 = ids_peak_ipl.PixelFormatName_BayerGB12
    
    
    #Return Types
    BUFFER = "buffer"
    """ids_peak.Buffer object"""
    CAM_IMAGE = "cam_image"
    """cam_image.Cam_Image object"""
    NDARRAY = "nd_array"
    """numpy.ndarray Object"""
    IPL_IMAGE = "ipl_image"
    """ids_peak_ipl.Image  Object"""
    
    
    #Sharpness Algorithms
    SHARPNESS_ALGORITHM_SOBEL = ids_peak_ipl.Sharpness.SharpnessAlgorithm_Sobel
    """ contrast-based sharpness algorithm (convolution)"""
    SHARPNESS_ALGORITHM_MEAN_SCORE = ids_peak_ipl.Sharpness.SharpnessAlgorithm_MeanScore
    """contrast-based sharpness algorithm (mean value)"""
    SHARPNESS_ALGORITHM_HISTOGRAM_VARIANCE = ids_peak_ipl.Sharpness.SharpnessAlgorithm_HistogramVariance
    """ statistics-based sharpness algorithm"""
    SHARPNESS_ALGORITHM_TENENGRAD = ids_peak_ipl.Sharpness.SharpnessAlgorithm_Tenengrad
    """ contrast-based sharpness algorithm (convolution)"""

class Connection:

    
    def __init__(self, quiet_mode=True) -> None:
        """Open a new connection with an IDS Device. The Device must be connected
        via USB3.0. 
        The default pixel format is set to RGB8, or Mono8 if the cam has a monochrome sensor.
        

        Args:
            quiet_mode (bool, optional): Will not print as much information when running various functions. Defaults to True.
        """        
        try:
            

            
            self.quiet_mode = quiet_mode #If True, messages are not printed
            try:
                ids_peak.Library.Initialize()
            except Exception as e:
                traceback.print_exc(e)
                self.printq("Failed to Initialise API Library")
            
            self.acquisition_running = False
            self.device = None
            self.TARGET_PIXEL_FORMAT_RGB = ids_peak_ipl.PixelFormatName_RGB8
            self.TARGET_PIXEL_FORMAT_MONO = ids_peak_ipl.PixelFormatName_Mono8
            self.pixel_format = None
            self.mono = None
            self.connected = False
            try:
                self.connected = self.open_connection()
            except Exception as e:
                self.connected = False
        except Exception as e:
            traceback.print_exc(e)            
            

    
    def open_connection(self) -> bool:
        """Find all connected devices and open a connection with the first.

        Returns:
            bool: True if successful connection opened, false otherwise.
        """        
        
        try:
            # Create instance of the device manager
            self.device_manager = ids_peak.DeviceManager.Instance()

            # Update the device manager
            self.device_manager.Update()
            # Return if no device was found
            if self.device_manager.Devices().empty():
                self.printq("Error: No device found!")
                return False

            # Open the first openable device in the managers device list
            for device in self.device_manager.Devices():
                if device.IsOpenable():
                    self.device = device.OpenDevice(ids_peak.DeviceAccessType_Control)
                    break
                else:
                    self.printq("Can't Open Device")
            
                # Return if no device could be opened
            if self.device is None:
                self.printq("Error - Device could not be opened!")
                return False   

            # Open standard data stream
            self.printq("Finding datastream...")
            self.datastreams = self.device.DataStreams()
            if self.datastreams.empty():
                self.printq("Error: Device has no DataStream!")
                self.device = None
                return False
            
            self.datastream: ids_peak.DataStream = self.datastreams[0].OpenDataStream()
            self.datastream_nodemap :ids_peak.NodeMap = self.datastream.NodeMaps()[0]
            self.datastream_nodemap.FindNode("StreamBufferHandlingMode").SetCurrentEntry("OldestFirst")
            
            self.printq("Opened datastream")
            
            # Get nodemap of the remote device for all accesses to the genicam nodemap tree
            self.nodemap = self.device.RemoteDevice().NodeMaps()[0]
            
            self.printq("Successfully Connected to Device")
            self.info = {"User ID" : str(self.node("DeviceUserID").Value()),
                     "Model": str(self.device.ModelName()),
                     "Serial Number": str(self.node("DeviceSerialNumber").Value())}
            
            #Check if RGB8 pixel format is available and set, and deactivate colour correction.
            #If not, device (probably) has monochrome sensor so set to 8 bit mono.
            
            if "RGB8" in [entry.SymbolicValue() for entry in self.node("PixelFormat").Entries()]:
                self.node("PixelFormat").SetCurrentEntry("BayerRG8")
                self.node("ColorCorrectionMode").SetCurrentEntry("Off")
                self.mono = False
            else:
                self.node("PixelFormat").SetCurrentEntry("Mono8")
                self.mono = True
 
            self.pixel_format = ids_peak_ipl.PixelFormat(self.node("PixelFormat").CurrentEntry().Value())
            
            
            for key, value in self.info.items():
                self.printq(f"{key}: {value}")
                
            return True
        except Exception as e:
            traceback.print_exc(e)
            return False
        
        
    def node(self, name:str) -> ids_peak.Node:
        """A shortcut for "self.nodemap.FindNode([node])".
        Retrieves a device node to query, set, or give a command

        Args:
            name (str): Name of node e.g "AcquisitionMode".

        Returns:
            ids_peak.Node: The named node, or None if it doesn't exist.
        """        
        try:
            if self.device is not None:
                return self.nodemap.FindNode(name)
            else:
                self.printq("Device not Connected")
        except Exception as e:
            self.printq(f"Node {name} does not exist on current device")
            return None
        
    
    def close_connection(self) -> bool:
        """Close the connection to the device.
        Stops acquisition if running and revokes all active Buffers

        Returns:
            bool: _description_
        """        
        try:
            # Stop Acquisition if it is still running
            self.stop_acquisition()
            # If a datastream has been opened, try to revoke its image buffers
            if self.datastream is not None:
                for buffer in self.datastream.AnnouncedBuffers():
                        self.datastream.RevokeBuffer(buffer)

            ids_peak.Library.Close()
            self.info = {}
            
        except Exception as e:
            traceback.print_exc(e)
            
    def alloc_and_announce_buffers(self)-> bool:
        """Allocates and announces buffers to be used for storing and transferring camera picture data.
        Revokes any existing buffers before allocating.

        Returns:
            bool: True if successful, False if exception thrown
        """        
        try:
            self.printq("Allocating and announcing buffers...")
            if self.datastream:
                # Flush queue and prepare all buffers for revoking
                self.datastream.Flush(ids_peak.DataStreamFlushMode_DiscardAll)
        
                # Clear all old buffers
                for buffer in self.datastream.AnnouncedBuffers():
                    self.datastream.RevokeBuffer(buffer)
        
                payload_size = self.node("PayloadSize").Value()
        
                # Get number of minimum required buffers
                num_buffers_min_required = self.datastream.NumBuffersAnnouncedMinRequired()
        
                # Alloc buffers
                for i in range(num_buffers_min_required):
                    buffer = self.datastream.AllocAndAnnounceBuffer(payload_size)
                    self.datastream.QueueBuffer(buffer)
        
                return True
        except Exception as e:
            traceback.print_exc(e)
            return False
    
    def capture_image(self, auto=False):
        image = None
        if auto:
            image = self.capture_auto_exposure()
        else:
            image = self.single_frame_acquisition()['image']
        
        image = self.create_cam_image(image, auto=auto)
        
        return image
        
    def capture_auto_exposure(self, init_microseconds=None):

                
                if init_microseconds is not None:
                    self.exposure_time(microseconds=init_microseconds)
                    
                self.printq("Auto Adjusting Integration Time")
                image_correctly_exposed = False # Assume image will be incorrectly exposed
                image = None
                while not image_correctly_exposed:
                    
                    image = self.single_frame_acquisition() #Capture image from device with current integration time setting
                    target_fraction = 0.01 #The target fraction of pixels to be oversaturated. 
                    target_margin = 0.005 #Images with fraction of pixel saturated above or below this margin are incorrectly exposed
                    
                    
                    circle_mask = cam_image.create_centre_mask(image, centre=[1226, 1034], radius=472)
                    fraction_white = cam_image.get_fraction_white_pixels(image, mask=circle_mask, saturation_threshold=250)
                    overexposed_difference = target_fraction - fraction_white #Calculate how far the image is from correct saturation level
                    exposure_time = self.exposure_time()
                    
                    
                    if abs(overexposed_difference) > target_margin: #If the image saturation is outside the margin of error perform adjustment
                        
                        self.printq(f"Incorrectly Exposed at {exposure_time/1000000}s")
                        self.printq(f"Fraction of pixels overexposed: {fraction_white}")
                        self.printq(f"Target Fraction: {target_fraction}")

                        #Calculate adjustment factor. The current integration time will be multiplied by this to get the new integration time guess.
                        #The factor is limited to between 2 and 0.5 (as sometimes small values can lead to crazy numbers)
                        
                        #The adjustment scales with the ralationship between the size of the saturation error and the target saturation fraction
                        #If the difference is large, the adjustment is large, and vice versa. This is fairly quick but could probably be optimised (Maybe with a PID type control?)
                        adjustment_factor = min(10, max(0.1, 1 - (fraction_white-target_fraction)/target_fraction ))
                        
                        self.printq("Adjustment factor: ", adjustment_factor)
                        #Calculate the new guess for a good integration time
                        new_integration  = exposure_time*adjustment_factor
                        
                        self.printq(f"Changing integration time to { self.exposure_time(microseconds=new_integration)/1000000}s")
                    else:
                        #If within the margin, exit the loop with the correctly exposed image
                        image_correctly_exposed = True
                        self.printq("############### Successful Adjustment ###############")
                        self.printq(f"Correctly Exposed at {exposure_time/1000000}s")
                        self.printq(f"Fraction of pixels overexposed: {fraction_white}")
                        self.printq(f"Target Fraction: {target_fraction}")
                return image
                    
    
    def create_cam_image(self, image:np.ndarray, auto:bool=False)-> cam_image.Cam_Image:
        
        image_depth = get_depth()

        image_exposure = self.exposure_time()
        image_gain = self.gain()
        
        image_temp = self.get_temperature()
        

        image_timestamp = datetime.now()
        

        format=self.node("PixelFormat").CurrentEntry().SymbolicValue()
    
        image = cam_image.Cam_Image(image=image,
                                timestamp = image_timestamp,
                                integration_time=image_exposure,
                                auto=auto,
                                gain=image_gain,
                                depth=image_depth,
                                cam_temp = image_temp,
                                sensor_temp=0,
                                format=format)
    
        return image
    
    def single_frame_acquisition(self) -> np.ndarray|bool:
        """Captures and returns an image using single frame acquisiton (SFA) mode.
        
        SFA is slower than Continous or other modes but saves power by not being active in between captures
        The device is returned to the previous acquisition mode after capture.
        Returns:
            cam_image.Cam_Image|bool: A Cam_Image object containing the image and metadata including time, and camera settings
        """        
        try:
            self.printq("Starting Single Frame Acquisition")
            
            current_mode = self.node("AcquisitionMode").CurrentEntry().SymbolicValue()# save previous acq. mode
            
            #Change to SFA and set to manual exposure start
            self.node("AcquisitionMode").SetCurrentEntry("SingleFrame")
            self.node("TriggerSelector").SetCurrentEntry("ExposureStart")
            self.node("TriggerMode").SetCurrentEntry("Off")
            
            self.start_acquisition()

            image = self.capture_frame()
            
            
            self.stop_acquisition() #Just in case, as in SFA mode acquisition should stop automatically after capture
            
            self.node("AcquisitionMode").SetCurrentEntry(current_mode)#return to previous mode
            self.printq("Got image")
            
            return image 
                   
            
        except Exception as e:
            traceback.print_exc(e)
            return False
    
    def start_acquisition(self) -> bool:
        """Locks critical device features, calls alloc_and_announce_buffers() and starts acquisition - buffers start filling immediately
        and image can be captured.
        Queues an ImageConverter instance for quick Conversion to correct pixel format after capture.

        Returns:
            bool: True if successful, else False
        """        
        try:
            self.printq("Starting Acquisition...")
            
            # Check that a device is opened and that the acquisition is NOT running. If not, return.
            if self.device is None:
                self.printq("No Device Connected")
                return False
            if self.acquisition_running is True:
                self.printq("Acquisition already running")
                return True
            
            self.alloc_and_announce_buffers()

            # Lock critical features to prevent them from changing during acquisition
            self.node("TLParamsLocked").SetValue(1)


            # Start acquisition on camera
            
            mode = self.node("AcquisitionMode").CurrentEntry().SymbolicValue()
            if mode == "SingleFrame":
                self.datastream.StartAcquisition(ids_peak.AcquisitionStartMode_Default)
            else:
                self.datastream.StartAcquisition(ids_peak.AcquisitionStartMode_Default, ids_peak.DataStream.INFINITE_NUMBER)

                
                
            self.node("AcquisitionStart").Execute()
            self.node("AcquisitionStart").WaitUntilDone()

            self.printq("Acquisition Started")
            self.printq("Acquisition Mode: ", mode )
            self.acquisition_running = True
            
            return True

        except Exception as e:
            traceback.print_exc(e)
            return False
    
    
    def stop_acquisition(self) -> bool:
        """Stops acquisition if running, flushes and revokes all buffers.
            
        Returns:
            bool: True if successfully stopped or already stopped, False if exception stops successful stop.
        """        
        try:
            self.printq("Stopping Acquisition...")
              # Check that a device is opened and that the acquisition is running. If not, return.
            if self.device is None or self.acquisition_running is False:
                self.printq("Device is None or acquisition is already stopped")
                return True
            
            self.node("AcquisitionStop").Execute()
            self.node("AcquisitionStop").WaitUntilDone()
            #TODO: Check Buffer Stream Mode: https://www.1stvision.com/cameras/IDS/IDS-manuals/en/stream-buffer-handling-mode.html
            # Stop and flush datastream
            self.datastream.StopAcquisition(ids_peak.AcquisitionStopMode_Default)
            self.datastream.Flush(ids_peak.DataStreamFlushMode_DiscardAll)
            
            for buffer in self.datastream.AnnouncedBuffers():
                self.datastream.RevokeBuffer(buffer)
       

            # Unlock parameters after acquisition stop

            self.node("TLParamsLocked").SetValue(0)
            self.printq("Unlocked TLP Parameters")

            self.acquisition_running = False
            self.printq("Acquisition Stopped")
            return True
            
        except Exception as e:
            traceback.print_exc(e)
            return False
    

    
        
    def capture_frame(self, return_type=Resources.NDARRAY) -> np.ndarray|ids_peak_ipl.Image|cam_image.Cam_Image:
        """Capture an image on the device. 
        Acquisition must be started.
        Flushes annd re-Queues buffers before capturing as they may be filled with images from when acquisition started.
        Gets camera settings for capture and other data, before creating and returning a Cam_Image object.
        Returns:
            np.ndarray
        """        
        try:
            
            self.printq("Capturing Image...")


            buff_time=max(2000, int(self.exposure_time()/1000)+500)

            if self.node("AcquisitionMode").CurrentEntry().SymbolicValue() in ["MultiFrame", "Continuous"] and False:
                self.printq("Flushing buffers")
                # Get buffer from device's datastream      
                #Flush previous buffers that may have taken images a while ago
                for buffer in self.datastream.AnnouncedBuffers():
                    #buffer = self.datastream.WaitForFinishedBuffer(buff_time)
                    if not buffer.IsQueued() and not buffer.IsAcquiring():
                        self.datastream.QueueBuffer(buffer)

            
            buffer = None
            attempts = 0
            while buffer is None:
                try:

                    buffer = self.datastream.WaitForFinishedBuffer(buff_time)
                except Exception as e:
                    buff_time += 100
                    attempts +=1
                    if attempts > 10:
                        traceback.print_exc(e)
                        break
            
            # Create IDS peak IPL image and convert it to RGBa8 format
            ipl_image = ids_peak_ipl_extension.BufferToImage(buffer)
            
            
            
            # Queue buffer so that it can be used again
            self.datastream.QueueBuffer(buffer)
            
            if return_type == Resources.IPL_IMAGE:
                return ipl_image
            
            
            # Get raw image data from converted image and construct a QImage from it
            image_np_array = ipl_image.get_numpy_1D()

            
            #converted_ipl_image = self.image_converter.Convert(
            #    ipl_image, self.pixel_format)


            width = ipl_image.Width()
            height = ipl_image.Height()

            format = ipl_image.PixelFormat().Name()
            self.printq("Format: ", format)
                
            img = image_np_array.reshape(height,width)

            if return_type == Resources.NDARRAY:
                return img.copy()
            
            if return_type == Resources.CAM_IMAGE:
                return self.create_cam_image(img.copy())
            


        except Exception as e:
            traceback.print_exc(e)
            return False
    
   
    
    def exposure_time(self, microseconds:int=None, seconds:float=None) -> int:
        """Query or Set exposure time.
        If time or seconds args are not set, just returns exposure time in microseconds,
        If microseconds OR seconds are set, the exposure time is set to that value, and the new value returned in microseconds.

        Args:
            microseconds (int, optional): New exposure length in microseconds. Defaults to None.
            seconds (float, optional): New exposure length in seconds. Defaults to None.
        Returns:
            int: _description_
        """    
        try:
            current_pixel_format = self.node("PixelFormat").CurrentEntry().SymbolicValue()
            if seconds is not None:
                if microseconds is None:
                    microseconds=int(seconds*1000000) #Convert seconds to microseconds
                else: 
                    self.printq("Can't Set both microseconds and seconds parameter. Using microseconds parameter value")
                    
            if microseconds is not None:
                sensor_mode = self.node("SensorOperationMode").CurrentEntry().SymbolicValue()
                max_exp = self.node("ExposureTime").Maximum()
                min_exp = self.node("ExposureTime").Minimum()
                
                if sensor_mode == "Default" and microseconds > max_exp:
                    self.change_sensor_mode("LongExposure")
                    self.printq("Changing to Long Exposure Mode")
                    max_exp = self.node("ExposureTime").Maximum()
                    min_exp = self.node("ExposureTime").Minimum()                    
                
                if sensor_mode == "LongExposure" and microseconds < min_exp:
                    self.change_sensor_mode("Default")
                    self.printq("Changing to Default Mode")
                    max_exp = self.node("ExposureTime").Maximum()
                    min_exp = self.node("ExposureTime").Minimum()
                     
                new_time = max(min_exp, min(max_exp, microseconds))
                self.node("ExposureTime").SetValue(new_time)
                
                self.node("PixelFormat").SetCurrentEntry(current_pixel_format)
            
            current_time=int(self.node("ExposureTime").Value())
            self.printq("Exposure Time: ", current_time)
            return current_time
        except Exception as e:
            traceback.print_exc(e)
    
    def gain(self, gain:float=None) -> float:
        """Query or set gain in dB
        If gain arg not passed, just returns current value,
        If gain arg is passed, sets and returns new value

        Args:
            gain (float, optional): Desired gain setting in dB. Defaults to None.

        Returns:
            float: gain in dB.
        """        
        try:
            if gain is not None:
                self.node("Gain").SetValue(float(gain))
                
            return self.node("Gain").Value()
        except Exception as e:
            traceback.print_exc(e)
    
    

            
    def get_temperature(self)-> float:
        """Query device temperature

        Returns:
            float: Device temperature in Degrees Celsius
        """        
        try:
            return self.node("DeviceTemperature").Value()
        except Exception as e:
            traceback.print_exception(e)

    
            
    def change_sensor_mode(self, mode:str="Default"):
        """Switch to different User settings profile

        Args:
            mode (str, optional): user set to switch to. Defaults to "Default".
        """        
        self.node("UserSetSelector").SetCurrentEntry(mode)
        self.node("UserSetLoad").Execute()
        self.node("UserSetLoad").WaitUntilDone()
        
    def save_settings(self, profile_number:int) -> bool:
        """Save current device settings to a user profile

        Args:
            profile_number (int): Profile number [0 or 1] to save to

        Returns:
            bool: True if succesful else False
        """        
        try:
            profile_name = ""
            if profile_number == 0:
                profile_name = "UserSet0"
            elif profile_number == 1:
                profile_name = "UserSet1"
            else:
                self.printq("Invalid profile_number argument: Must be 0 or 1")
            # Save user settings
            self.node("UserSetSelector").SetCurrentEntry(profile_name)
            self.node("UserSetSave").Execute()
            self.node("UserSetSave").WaitUntilDone()
            return True
        except Exception as e:
            traceback.print_exc(e)
            return False
    
    # Load default user settings
    def load_settings(self, name:str=None) -> bool:
        """Load settings profile from user defined sets or default

        Args:
            name (str, optional): Name of set to load in. Defaults to None.

        Returns:
            bool: True if successfully loaded, else False
        """        
        try:
            profile_name = name
            if name is None:
                profile_name = "Default"
            elif profile_name == "0":
                profile_name = "UserSet0"
            elif profile_name == "1":
                profile_name = "UserSet1"
                
                
            # Load default user settings
            self.node("UserSetSelector").SetCurrentEntry(profile_name)
            self.node("UserSetLoad").Execute()
            self.node("UserSetLoad").WaitUntilDone()
            
            return True
        except Exception as e:
            traceback.print_exc(e)
            return False
    
    
    def save_settings_as_default(self) -> bool:
        """Save current settings as default

        Returns:
            bool: True if successful
        """        
        try:
            current_profile = self.node("UserSetSelector").CurrentEntry()
            self.node("UserSetSelector").SetCurrentEntry(current_profile)
            return True
        except Exception as e:
            traceback.print_exc(e)
            return False
        
        

    def set_all_to_manual(self) -> bool:
        """Set all Image related camera settings to manual.
        Turns off auto gain, white balance, exposure time, and colour correction 

        Returns:
            bool: True if successful
        """        
        try:
            auto_nodes = ["BalanceWhiteAuto", "GainAuto", "ExposureAuto", "ColorCorrectionMode"]
            for node_name in auto_nodes:
                try:
                    self.node(node_name).SetCurrentEntry("Off")
                    return True
                except Exception as e:
                    self.printq(f"Could not set value of node '{node_name}'")
        except Exception as e:
            traceback.print_exc(e)
            return False
    
    def sharpness_test(self) -> float:
        return self.single_frame_acquisition()['sharpness']
    
    def printq(self, *args, **kwargs):
        """Only prints if Connection instance quiet mode is set to False
        """        
        if not self.quiet_mode:
            print(*args, **kwargs)

def make_ROI_start_centre(image:ids_peak_ipl.Image, centre:tuple[int]=None, size:int|tuple[int]=None) -> ids_peak_ipl.Rect2D:

    if size is None:
       return ids_peak_ipl.Rect2D(ids_peak_ipl.Point2D.New(x = 0, y=0), ids_peak_ipl.Size2D.New(width=image.Width(), height=image.Height())) 
    
    if isinstance(size, int):
        size = (size, size)
    
    print("Size: ", size)
    
    if centre is None:
        centre = (image.Width()/2, image.Height()/2)
        
    top_left = (int(centre[0] - size[0]/2),int(centre[1] - size[1]/2))
    
    print("Top Left: ", top_left)
    
    
    if top_left[0] + size[0] > image.Width() or top_left[1] + size[1] > image.Height() or min(top_left) < 0:
         raise ValueError((f"ROI rectangle does not fit in image\n" 
                           f"Image size:{image.Width()}x{image.Height()}\n"
                           f"Rectangle bounds: Left: {top_left[0]} Top: {top_left[1]} Right: {top_left[0]+size[0]} Bottom: {top_left[1]+size[1]}"))

    
    return ids_peak_ipl.Rect2D(ids_peak_ipl.Point2D.New(x = top_left[0], y=top_left[1]), ids_peak_ipl.Size2D.New(width=size[0], height=size[1]))
    


def make_ROI_start_top_left(image:ids_peak_ipl.Image=None, start_point:tuple[int]=(0,0), size:int|tuple[int]=None) -> ids_peak_ipl.Rect2D:
    

    top_left = start_point
    
    if size is None:
        size = (image.Width() - top_left[0], image.Height() - top_left[1])
           
    if isinstance(size, int):
        size = (size, size)

    if min(top_left) < 0:
        raise ValueError(f"Start point coordinates must be zero or greater - Coordinates given: {top_left}")
            
    if top_left[0] + size[0] > image.Width() or top_left[1] + size[1] > image.Height():
        raise ValueError(f"ROI rectangle does not fit in image\nImage size:{image.Width()}x{image.Height()}\nRectangle bounds: Left: {top_left[0]} Top: {top_left[1]} Right: {top_left[0]+size[0]} Bottom: {top_left[1]+size[1]}")
    
    return ids_peak_ipl.Rect2D(ids_peak_ipl.Point2D.New(x = top_left[0], y=top_left[1]), ids_peak_ipl.Size2D.New(width=size[0], height=size[1]))

def get_ROI_bounds(roi: ids_peak_ipl.Rect2D) -> tuple[int]:
    """
    Get the bounds of the Region of Interest (ROI).

    Args:
        roi (ids_peak_ipl.Rect2D): The ROI object.

    Returns:
        tuple[int]: A tuple containing the left, top, right, and bottom coordinates of the ROI.

    """
    return (roi.left(), roi.top(), roi.right(), roi.bottom())



def make_ROI_from_bounds(left:int, top:int, right:int, bottom:int) -> ids_peak_ipl.Rect2D:
    """
    Create a Rect2D object using left, top, right, and bottom bounds.

    Args:
        left (int): The left coordinate of the ROI.
        top (int): The top coordinate of the ROI.
        right (int): The right coordinate of the ROI.
        bottom (int): The bottom coordinate of the ROI.

    Returns:
        ids_peak_ipl.Rect2D: The Rect2D object representing the ROI.
    """
    return ids_peak_ipl.Rect2D(ids_peak_ipl.Point2D.New(x=left, y=top), ids_peak_ipl.Size2D.New(width=right-left, height=bottom-top))
      
def calculate_sharpness(image:ids_peak_ipl.Image, roi:ids_peak_ipl.Rect2D=None, algorithm=ids_peak_ipl.Sharpness.SharpnessAlgorithm_Sobel)->float:
    """Calculates image sharpness using the IDS IPL library. 
    
    Default algorithm is Sobel Convolution. 
    See IDS docs for algorithm details

    Args:
        image (ids_peak_ipl.Image): IPL image to be processed
        roi (ids_peak_ipl.Rect2D, optional): Region of Interest where sharpness will be calculated - Leave as None to make region full image, or create with make_ROI_start_top_left() or make_ROI_start_centre(). Defaults to None.

    Returns:
        float: _description_
    """    
    try:

        if roi is None:
            roi = make_ROI_start_top_left(image)
        sharp_calc = ids_peak_ipl.Sharpness()
        sharp_calc.SetROI(roi)
        
        image.ConvertTo(ids_peak_ipl.PixelFormatName_Mono8)
        
        return sharp_calc.Measure(image)
    
    
    except Exception as e:
        traceback.print_exc(e)
        return None
    
def convert_image(image:ids_peak_ipl.Image, target_format:str)->ids_peak_ipl.Image:    
        return image.ConvertTo(target_format)
        
        
def get_depth() ->float|bool:
    """Dummy function to simulate checking for depth at time of image capture.
    May be removed to be implemented in other modules as it is not directly related
    to IDS device connection.

    Returns:
        float|bool: Always returns 0. Will return depth if functionality implemented.
    """    
    try:
        
        return 0
    
    except Exception as e:
            traceback.print_exc(e)
            return False

