# TRITON

![A Blue Psi symbol on a white background](https://raw.githubusercontent.com/ru-wallace/resources/main/triton/triton_long_small.png)

**T**ool for **R**adiance and **I**rradiance **T**esting **O**ptically in **N**ature

## Description

This is a project in development containing tools which can be used for controlling IDS Cameras, and processing images captured.
The tools will only work on Linux based operating systems. The system is designed to be used with a Raspberry Pi 4.

## Requirements

- Linux computer (Project was developed using Raspberry Pi OS on an RPi4).
- USB 3.0 port (or faster).
- IDS Device compatible with the IDS Peak API.
- [IDS Peak API](https://en.ids-imaging.com/ids-peak.html) libraries installed.
- Python 3.11 (This is the newest version supported by the IDS Peak API).
- A  Conda python environment with the required [dependencies](./environment.yml) installed. (Some of the dependencies are not available on conda channels and Pip must be used while the Conda environment is active). The IDS Libraries must be manually installed using the wheel files included in the IDS Peak download (see [installation](#installation)).

    Anaconda can be tricky to set up on a Raspberry Pi. The [Miniforge](https://github.com/conda-forge/miniforge) project is a useful tool which has installers which are specifically for Raspberry Pi OS (Requires a 64-bit version of Raspberry Pi OS).

### Recommendations

- An RTC (Real time clock) module if using Raspberry Pi or other device without a hardware clock. Enables accurate time keeping when disconnected from the internet.

## Installation

- Download and install the IDS Peak Software

- Create a python virtual environment and install the necessary dependencies in environment.yml. With conda this can be done using:

        conda env create -f environment.yml

- Activate this environment using:

        conda activate [environment name] 
- To install the IDS Peak Python Libraries make sure your python environment is activated and use:

        pip install --no-deps [.whl file location]

    Make sure to use the correct location of the file corresponding to your system architecture (ARM64 for Raspberry Pi 4).

    Conda has no built-in function for installing modules from .whl wheel files but using pip will install it in the environment. The "--no-deps" option ensures that only the IDS files will be installed and not any of their listed dependencies. Use conda where possible to install any dependencies which are required beyond that.

- Run the install script by navigating to the install directory and using:

        sudo bash bash_scripts/install.sh

  You must use sudo as the install script modifies a system setting for the USB IO buffer memory size ([See this page in the IDS Peak manual for details](https://www.1stvision.com/cameras/IDS/IDS-manuals/en/operate-usb3-hints-linux.html)).

  This script allows you to use the command:

        runcam [options]

  from the terminal, regardless of current directory.
  The install script also creates a ".env" file in the ```./python_scripts/``` subdirectory. This is where we store environment variables that are used throughout the program, mainly the locations of directories.

- Update the new ```./python_scripts/.env``` file:
  - If you want to specify the default location in which data files and camera routine files are stored, edit the line:
            DATA_DIRECTORY="[desired location of output files]"

    Make sure there are no spaces before or after the '=' and insert your desired location.
    e.g if your username is ```user1```:

            DATA_DIRECTORY="/home/user1/radiance_files"

    If this is not set, the default directory will be set as a subfolder of the directory where this code is, named ```TRITON/```.

    Data captured by the camera and processed by TRITON will be kept in the ```sessions/``` subdirectory of this.
    Routine files which are used to define instructions for auto capture are kept in the ```routines/``` subdirectory of the data directory.

  - If needed, edit the other three lines to reflect the location of the directory in which IDS Peak is installed. By default this is in ```/opt/[ids_peak_version]/....```
  
## Concepts

### Device Communication

The application operates the camera using an implementation of the IDS Peak API in the ids_interface.py file. Functions are provided to control all of the features of an IDS Peak Ueye+ USB 3 camera. Both Colour and Monochrome devices are supported. On loading the device, all automatic features of the camera such as auto-exposure, auto-gain and colour correction are turned off. The device is configured to use BayerRG8 or Mono8 pixel formats for colour and monochrome devices respectively. This means that the raw digital data is returned in 8-bit format.

A custom algorithm for adjusting integration time automatically is used, though for very low light it can be slow.

### Sessions

A session (for want of a better name) is a set of images stored together in a single directory. It is intended that one session be used for one related set of measurements (e.g one run of calibration images, or one drop of the device from a ship) A session has the following attributes:

- Name
- Start time
- Co-ords (optional)
- Notes (Not yet implemented)
- Images

Each session is stored in the ```[data directory]/sessions/``` subdirectory in a directory with the same name as the session.
The directory contains the following files:

- ```log.json```: Every session has this file. it contains a list of each image captured in the session, metadata including the time, number, camera temperature, integration time, gain, depth (yet to be implemented), and the raw and processed measurements calculated for that image (see [Image Processing](#image-processing)).
- ```run_log.txt```: If any images in the session are captured using an auto-capture routine, this file will be present. It contains the output of the auto_capture.py python script as it executes the routine. This is useful for debugging if there is an issue with the routine running.
-```run_[number].csv```: Every time a routine is run which adds images to the session , a new run csv file is added which contains all the white balance and pixel averages of each photo as well as the exposure time and device temperatures.
-```[numbers].png``` The Image files.

### Image Processing

The images are processed using the cam_image script. To measure various attributes, the following regions are used:

![Regions Diagram](https://raw.githubusercontent.com/ru-wallace/resources/main/triton/regions.png)

- **Inner Region**: The active area of the sensor. Due to the fisheye lens, this is a circle roughly centered on the middle of the sensor.
- **Outer Region**: The dark area of the sensor recieving no direct light from the lens.
- **Margin**: A margin surrounding the inner region which is excluded from the outer region. When the image is bright due to high luminance or a long integration time, a 'halo' of light bleeds into the outer region. As long as an image is not highly over-exposed, the margin should avoid the bleed from significantly affecting dark level measurements.
- **Corner Regions**: A quarter-circle area in each corner used to measure the furthest extremes of the sensor, away from the active area. For each measurement a single value is calculated averaging over each corner.
  The outer region also includes these regions.

#### White Fraction

For each region, the fraction of pixels which are saturated is calculated. This is quantified as the number of pixels with a value greater than 250 (out of 255) divided by the total number of pixels in the region. This quantity is referred to as the "*white fraction*" and ranges from 0 (no saturated pixels) to 1 (all pixels saturated).

#### Pixel Averages

For each region, an average pixel value for each colour channel is then calculated. This is done prior to demosaicing so that the raw unaltered sensor values can be used.

#### Luminance

Explanation of Luminance Calcs ----------------------------
###################### ################################# ################ ######################## ########### ####################### ############################ ######################################### #############

#### Auto adjustment of integration time

For the inner active region the white fraction is used to drive the auto-adjustment of integration time if used. A test image is taken and the inner white fraction calculated. This is compared against a target white fraction - 0.01  (1% saturation) by default.

The integration time is increased or decreased proportionally to get closer to the target fraction, and the process repeated until within 0.005 of the target. For short integration times below 1/10th of a second this is trivial, but can be time consuming for longer captures, especially into the tens of seconds.






## Usage

There are two main tools in the project - a menu-based console interface, and a tool to run an auto-capture routine with a set of pre-defined instructions.

### Console Interface

This is used for live control of a camera, as well as viewing details of existing images that have been captured.

Launch the console interface using the command:

        runcam -c

This will open 