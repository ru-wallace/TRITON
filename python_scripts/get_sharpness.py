import ids_interface
import sys
import time
import threading
import traceback


class Sharpness_Tool:
    def __init__(self) -> None:
         
        self.device = ids_interface.Connection(quiet_mode=True)

        if not self.device.connected:
                    print("Could not connect to self.device")
                    sys.exit(1)
                    
        self.count = 0

        self.device.stop_acquisition()

        self.device.load_settings("Default")
        self.device.node("PixelFormat").SetCurrentEntry("Mono8")
        self.device.node("AcquisitionMode").SetCurrentEntry("Continuous")
        self.exposure_time = self.device.integration_time(microseconds=150)
        self.device.node("ExposureAuto").SetCurrentEntry("Continuous")
        self.device.start_acquisition()
        self.last_error = None
        self.error_count = 0
        self.cam_active = False
        self.error = False
        self.ROI = None
        self.auto = False
        
        while self.error_count < 5:
            
            try:
                self.error = False
                #self.auto = self.count == 0

                self.capture()
                self.count += 1
                if self.count > 40:
                    self.count = 0

            
                
            except KeyboardInterrupt:
                print("")
                print("Exiting...")
                break
            except Exception as e:
                traceback.print_exception(e)
                self.error = True
                self.last_error = e
            finally:
                self.error_count += self.error
                if self.error_count > 4:
                    print("")
                    print("Too many errors. Quitting.")
                    traceback.print_exception(self.last_error)
                    break
                pass
            
        print("Closing self.device connection")   
        
        
        self.device.stop_acquisition()
        self.device.close_connection()
    
    
    
    
    def capture(self, auto=False):
        try:
            #print(f"Capturing - Exposure time: {self.device.exposure_time()/1e6}s")
            sys.stdout.flush()
            image = self.device.capture_frame(return_type=ids_interface.Resources.IPL_IMAGE)
            sharpness_thread = threading.Thread(target=self.print_sharpness, args=(image,))
            sys.stdout.flush()
            sharpness_thread.start()
        except KeyboardInterrupt:
            self.error = True
            self.error_count = 10
        except Exception as e:
            traceback.print_exception(e)
            self.error = True
            self.last_error = e

            
    def print_sharpness(self, image):
        try:
            if not self.ROI:
                self.ROI = ids_interface.make_ROI_start_centre(image, size=600)
                    
            sharpness = ids_interface.calculate_sharpness(image, self.ROI)
            print(f"Sharpness: {round(sharpness, 2)} Integration Time: {self.exposure_time/1000000}s ({self.exposure_time}μs)", end=f"   \r", flush=True)
            sys.stdout.flush()
        except Exception as e:
            self.last_error = e
            self.error_count +=1
                

if __name__ == "__main__":
    try:
        Sharpness_Tool()
    except KeyboardInterrupt:
        print("Exiting...")