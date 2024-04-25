import ids_interface
import sys
import time

device = ids_interface.Connection(quiet_mode=True)

if not device.connected:
            print("Could not connect to Device")
            sys.exit(1)
            
count = 5

device.exposure_time(microseconds=150)

while True:
    if count == 5:
        count = 0
        device.capture_auto_exposure()
        continue
    
    print("Sharpness: ", round(device.sharpness_test(), 2), end="\r")
    count += 1
    time.sleep(1)