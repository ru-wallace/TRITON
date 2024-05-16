import numpy as np
import time
import device_interface
import traceback

def calc_focus(image_array:np.ndarray, integration_time_us, shape, *args):
    image_array = image_array.reshape(shape)
    height, width = shape
    centre_array = image_array[int(height/2-height/6):int(height/2+height/6), int(width/2-width/6):int(width/2+width/6)]
    gy, gx = np.gradient(centre_array)
    gnorm = np.sqrt(gx**2 + gy**2)
    sharpness = np.average(gnorm)
    print(f"Sharpness: {round(sharpness, 2)} - Int Time: {str(round(integration_time_us/1e3, 2)).ljust(6, '0')}ms - T: {round(cam.temp)}°C                ", end="\r", flush=True)
    

cam:device_interface.Camera = device_interface.Camera()
cam.set_to_manual()
cam.set_auto_params(target=240, tolerance=5, percentile=10, max_int=100, time_unit=device_interface.MILLISECONDS)

cam.integration_time(150)
cam.start_continuous_capture(callback=calc_focus, auto=True, callback_as_thread=True)


capturing = True
while capturing:
    try:
        time.sleep(0.01)
    except KeyboardInterrupt:
        cam.stop_continous_capture()
        capturing = False
        print("\nExiting...")
        break
    except Exception as e:
        traceback.print_exception(e)
        break

while cam.acquiring:
    time.sleep(0.01)
    print("Exiting...                                                                                                  ", end="\r")
    
print("\nDone")


    