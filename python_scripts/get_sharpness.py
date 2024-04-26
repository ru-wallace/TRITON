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

        self.device.set_all_to_manual()
        self.device.stop_acquisition()
        self.device.node("AcquisitionMode").SetCurrentEntry("SingleFrame")
        self.device.load_settings("Default")
        self.exposure_time = self.device.exposure_time(microseconds=150)

        self.error_count = 0
        self.cam_active = False
        self.error = False
        
        while self.error_count < 5:
            
            try:
                self.error = False
                self.auto = self.count == 0
                
                
                if not self.cam_active:
                    try:
                        
                        cam_thread = threading.Thread(target=self.start_cam_thread, args=(self.auto,))
                        cam_thread.start()
                        self.count += 1
                        if self.count > 5:
                            self.count = 0
                    except KeyboardInterrupt:
                        print("")
                        print("Exiting...")
                        break
                    except:
                        self.error = True
                
                if not self.error:
                    self.error_count = 0
                
            except KeyboardInterrupt:
                print("")
                print("Exiting...")
                break
            except:
                self.error = True
            finally:
                self.error_count += self.error
                if self.error_count > 4:
                    print("")
                    print("Too many errors. Quitting.")
                    break
                pass
            
        print("Closing self.device connection")   
        self.device.stop_acquisition()
        self.device.close_connection()
    
    def start_cam_thread(self, auto=False):
        try:
            if self.cam_active or self.error_count > 4:
                return
            
            self.cam_active = True
            
            if auto:
                self.device.capture_auto_exposure()
                self.exposure_time = self.device.exposure_time()

            print(f"Sharpness: {round(self.device.sharpness_test(), 2)} Integration Time: {self.exposure_time/1000000}s ({self.exposure_time}us)", end=f"   \r")
            
            
        except KeyboardInterrupt:
            self.error = True
            self.error_count = 10
        except Exception as e:
            traceback.print_exc(e)
            self.error = True
        finally:
            self.cam_active = False
if __name__ == "__main__":
    try:
        Sharpness_Tool()
    except KeyboardInterrupt:
        print("Exiting...")