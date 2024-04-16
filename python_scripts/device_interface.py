from harvesters.core import Harvester
import os
import numpy as np
from datetime import datetime, timedelta
import traceback
from cam_image import Cam_Image

PRODUCER_PATH = os.environ.get('PRODUCER_PATH')
PRODUCER_PATH = "/opt/ids-peak-with-ueyetl_2.7.1.0-16417_arm64/lib/ids/cti/ids_u3vgentl.cti"


class Camera:
    def __init__(self) -> None:
        h = Harvester() 
        
        #ADD produce file path
        h.add_file(PRODUCER_PATH)
        h.update()
        self.device = h.create()
        self.nodemap = self.device.remote_device.node_map
        self.data_stream = self.device.data_streams[0]
        print("Datastream:")
        print(self._query_node_list("Buffer", nodemap=self.data_stream.node_map))
        self.data_stream.node_map.StreamBufferHandlingMode.set_value("NewestOnly")
        #Reset device timestamp to zero
        self.nodemap.TimestampReset.execute()
        self.start_time = datetime.now()
        self.clock_tick_length = 1/self.nodemap.DeviceClockFrequency.value

        #Set Pixel Format to BayerRG8 if available, else set to Mono8
        if "BayerRG8" in self._valid_pixel_formats():
            self.nodemap.PixelFormat.set_value("BayerRG8")
        else:
            self.nodemap.PixelFormat.set_value("Mono8")
        
        
        
        # Activate chunk mode and enable pixelformat and exposure time chunks so the device passes this data along with the image
        self.nodemap.ChunkModeActive.set_value("True")
        for entry in self.nodemap.ChunkSelector._get_symbolics():
            if entry in ["ExposureTime", "PixelFormat"]:
                print(f"Setting {entry} to True")
                self.nodemap.ChunkSelector.set_value(entry)
                self.nodemap.ChunkEnable.set_value("True")
                
    
              
    def capture_image(self, auto=False):
        try:
            #print("Min Buffers: ", self.data_stream.NumBuffersAnnouncedMinRequired())
            self.auto_exposure_device(auto)
                
            self.device.start()
            image_array = None
            
            
            with self.device.fetch() as buffer:
                image = buffer.payload.components[0].data
                
                image_array = np.array(image).reshape(buffer.height, buffer.width).copy()
                
                format = buffer.payload.components[0].data_format
                print("Format: ", format)
                
                clock_timestamp = buffer.timestamp_ns/(10**9)
                
                timestamp = self.start_time + timedelta(seconds = clock_timestamp)
                buffer.update_chunk_data()
                
                
                
                exposure_time = self.nodemap.ChunkExposureTime.value
                print("Exposure time: ", exposure_time)
                #print("Brightness Auto Status: ", self.nodemap.BrightnessAutoStatus.value)
                
                
            self.device.stop()  
            return Cam_Image(image_array,  format=format, timestamp = timestamp, integration_time = exposure_time, gain = 1, temp = 0, depth = 0 )
        except Exception as e:
            traceback.print_exc(e)
            return None    
    
    
    def auto_exposure_device(self, on=True):
        if not on:
            self.nodemap.GainAuto.set_value("Off")
            self.nodemap.ExposureAuto.set_value("Off")
            return self.nodemap.ExposureAuto.value == "Off"
        self.nodemap.BrightnessAutoFramerateLimitMode.set_value("Off")
        self.set_exposure_time(seconds=0.001)
        

        self.nodemap.GainAuto.set_value("Off")
        self.nodemap.ExposureAuto.set_value("Off")
        self.set_exposure_time(seconds=0.001)
        self.nodemap.BrightnessAutoExposureTimeLimitMode.set_value("Off")
        self.nodemap.BrightnessAutoPercentile.set_value(5)
        self.nodemap.BrightnessAutoTarget.set_value(250)
        self.nodemap.BrightnessAutoTargetTolerance.set_value(1)
        self.nodemap.ExposureAuto.set_value("Continuous")

        
        
        
        old_mode = self.nodemap.SensorOperationMode.value
        mode = ""
        time = None
        self.capture_empty_until_stable()
        print("--")

        print("Device Exposure Time: ", self.nodemap.ExposureTime.value)
        
        if self.nodemap.ExposureTime.value == self.nodemap.ExposureTime.max and old_mode != "LongExposure":
            mode = "LongExposure"
        elif self.nodemap.ExposureTime.value == self.nodemap.ExposureTime.min and old_mode == "LongExposure":
            mode = "Default"
    
        if mode != "":
            
            self.load_set(mode)
            self.nodemap.BrightnessAutoFramerateLimitMode.set_value("Off")
            
            
        
        self.capture_empty_until_stable()
        print("Device Exposure Time: ", self.nodemap.ExposureTime.value)
            
        self.nodemap.ExposureAuto.set_value("Continuous")
        

        self.print_settings()
          
        return self.nodemap.ExposureAuto.value == "Continuous"

    
    def set_exposure_time(self, seconds):
        try:
            self.nodemap.ExposureAuto.set_value("Off")
            new_time = max(self.nodemap.ExposureTime.min, min(self.nodemap.ExposureTime.max, int(seconds*(10**6))))
            self.nodemap.ExposureTime.set_value(new_time)
            return True
        except Exception as e:
            print("Problem setting exposure time")
            traceback.print_exc(e)
            return False

    def set_pixel_format(self, pixel_format):
        try:
            self.nodemap.PixelFormat.set_value(pixel_format)
            return True
        except:
            return False

    def capture_empty_image(self, number=1):
        print(f"Capturing {number} empty images")
        
        for i in range(number):
            self.device.start()
            with self.device.fetch() as buffer:
                buffer.update_chunk_data()
                time = self.nodemap.ChunkExposureTime.value
                print("Empty image - Exposure Time: ", time/10**6, "S")
            self.device.stop()
        
    def capture_empty_until_stable(self):
        print("Capturing empty images until stable")
        stable = False
        last_exposure_time = 0
        iterations = 0
        while not stable:
            #self.capture_empty_image(3)
            self.device.start()
            with self.device.fetch() as buffer:
                buffer.update_chunk_data()
                time = self.nodemap.ChunkExposureTime.value
                print("Empty Image - Exposure Time: ", time/10**6, "S")
                if time == last_exposure_time:
                    stable = True
                last_exposure_time = time
            self.device.stop()
            self.data_stream.flush()
            iterations += 1
        print("Final Exposure Time: ", last_exposure_time/10**6, "S")
        print("Iterations: ", iterations)
        
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
            traceback.print_exc(e)
        
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
                
        
if __name__ == "__main__":
    c = Camera()
    c._query_node_list("Flush")
    image = c.capture_image(auto=True)
    #c._query_node_list("AutoExposure")
    