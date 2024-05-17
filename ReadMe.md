# AEGIR

**A**rtifically and **E**nvironmentally **G**enerated **I**rradiance and **R**adiance

## Description

This is a project in development which can be used for controlling IDS USB3Vision Cameras, and processing images captured.
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

- Run the install script by navigating to the main directory and using:

        sudo bash bash_scripts/install.sh

  You must use sudo to run the script as the root user as the install script modifies a system setting for the USB IO buffer memory size ([See this page in the IDS Peak manual for details](https://www.1stvision.com/cameras/IDS/IDS-manuals/en/operate-usb3-hints-linux.html)) and modifies the permissions of files in the application.
  
  The script asks for the directory in which the user would like captured data to be stored, and the location of the ids peak installation so that the drivers for the IDS camera can be used.
  It creates a ".env" file in the main installation directory containing environment variables used for running AEGIR.
  It creates a directory in the specified location (by default in the ```/home/[user]/``` directory), and creates two further sub-directories - ```routines``` and ```sessions``` - which will be the location in which routines will be read and captured data stored respectively. Example routines are included in the ```routines``` directory.

  Once the installation has completed successfully, you can run the application from the shell from any location using:

        runcam [options]  
  
## Usage

## Concepts

### Device Communication

The application operates a camera using an implementation of the [*GenICam*](https://www.emva.org/standards-technology/genicam/) *GenTL* API  in the device_interface.py file. The Harvesters Image Acquisition Engine package for Python as maintained by the GenICam committee is used to generate images.
Functions are provided to control all of the features of an IDS Peak UEye+ USB 3 camera. Both Colour and Monochrome devices are supported. On loading the device, all automatic features of the camera such as auto-exposure, auto-gain and colour correction are turned off. The device is configured to use BayerRG8 or Mono8 pixel formats for colour and monochrome devices respectively. This means that the raw digital data is returned in 8-bit format.

A custom algorithm for adjusting integration time automatically is used, though for very low light it can be slow.

### Sessions

A session is a set of images stored together in a single directory. It is intended that one session be used for one related set of measurements (e.g one run of calibration images, or one drop of the device from a ship).

A session has the following attributes:

- Name
- Start time
- Images

Each session is stored in the ```[data directory]/sessions/``` subdirectory in a directory with the same name as the session.
The directory uses the following structure:

        .../AEGIR_DATA/sessions/[session name]/
        |       images/
        |       |.......[session_name]_000.png
        |       |.......[session_name]_001.png
        |       |.......[session_name]_002.png
        |       |.......etc..
        |
        |.......session.json
        |.......images.csv
        |.......output.log

-```images/```: A subdirectory containing the image files as PNGs. Each image file has its metadata embedded in the file, which can be accessed in various ways, including using the Python Image Library (PIL) Image.metadata() function. As a last resort, opening the image using notepad or a similar text editor will also show the data in slightly mangled plain text, along with the binary pixel data of the image.

- ```session.json```: A JSON formatted list of each image captured in the session, and metadata including the time, number, camera temperature, integration time, gain, and the raw and processed measurements calculated for that image (see [Image Processing](#image-processing)).

- ```images.csv```: Every time a routine is run which adds images to the session , a new run csv file is added which contains all metadata for each image.

- ```output.log```: This file contains the output of the auto_capture.py python script as it executes the routine. This is useful for debugging if there is an issue with the routine running.

### Routines

### Image Processing

#### Image Regions

The images are processed using the cam_image.py script. To measure various attributes, the following regions are used:

![Regions Diagram](https://raw.githubusercontent.com/ru-wallace/resources/main/triton/regions.png "Diagram of the regions used when processing images")

- **Inner Region**: The active area of the sensor. Due to the fisheye lens, this is a circle roughly centered on the middle of the sensor.
- **Outer Region**: The dark area of the sensor recieving no direct light from the lens.
- **Margin**: A margin surrounding the inner region which is excluded from the outer region. When the image is bright due to high luminance or a long integration time, a 'halo' of light bleeds into the outer region. As long as an image is not highly over-exposed, the margin should avoid the bleed from significantly affecting dark level measurements.
- **Corner Regions**: A quarter-circle area in each corner used to measure the furthest extremes of the sensor, away from the active area. For each measurement a single value is calculated averaging over each corner.
  The outer region also includes these regions.

The program also calculates saturation fractions for concentric rings expanding out from the inner region.

#### Saturation Fraction

For each region, the fraction of pixels which are saturated is calculated. This is quantified as the number of pixels with a value greater than 250 (out of 255) divided by the total number of pixels in the region. This quantity is referred to as the "*white fraction*" and ranges from 0 (no saturated pixels) to 1 (all pixels saturated).

#### Pixel Averages

For each region, an average pixel value for each colour channel is calculated, or a single value for monochrome.

#### Luminance

To calculate absolute luminance, first relative luminance is ascertained and then a formula applied taking into account gain, integration time, and aperture settings.

##### Relative Luminance

###### *Monochromatic Camera*

For a monochromatic camera, relative luminance is simple, as the pixel values are already a measure of luminance. The white point for the camera is 255, and black point is 0. The pixels are normalised to between 1 and 0 by dividing each value by 255. The mean pixel value of the inner region is then taken as the relative luminance.
  
###### *Colour Camera*

For a colour camera capturing data in 8bit RGB, a more complex process is used to ascertain relative luminance. Again the pixel values are normalised to between 0 and 1 by dividing by 255:

${C}'_{sRGB} = \frac{\left (C_{8bit}-KDC  \right )}{\left (WDC-KDC  \right )} \qquad \left (1  \right )$

${C}'_{sRGB} = C_{8bit} \div {255} \qquad \text{ } \left (2  \right )$

Where $C_{8bit}$ is the pixel value between 0 and 255 for each channel, KDC is the black digital count of 0, and WDC is the white digital count of 255.

The camera captures data in the non linear sR'G'B' colour space. Using a procedure defined in *IEC Standard 61966-2-1/AMD1:2003 Section 5.2*, the pixel values are linearised:

$C_{sRGB} = \left\{\begin{matrix}
C'_{sRGB} \div 12.92 & \text{if }  C'_{sRGB} \leq 0.0405 \\
\left [ \frac{\left( C'_{sRGB} + 0.055 \right )}{1.055}  \right]^{2.4} & \text{if } C'_{sRGB} > 0.0405 \\
\end{matrix}\right.  \quad \left (3 \right )$

The mean value for each channel is taken for pixels within the [inner region](#image-regions), and the resulting linear sRGB values are transformed into the CIE 1931 XYZ colour space using:

$\begin{bmatrix}
X\\
Y\\
Z
\end{bmatrix}= \begin{bmatrix}
0.4124 & 0.3576 & 0.1805 \\
0.2126 & 0.7152 & 0.0415 \\
0.0193 & 0.1192 & 0.9505
\end{bmatrix}\begin{bmatrix}
R_{sRGB} \\
G_{sRGB} \\
B_{sRGB}\end{bmatrix} \qquad \text{     }\left(4 \right )$

In which the Y value corresponds to the luminance.

##### Absolute Luminance



#### Auto adjustment of integration time

For the inner active region the white fraction is used to drive the auto-adjustment of integration time if used. A test image is taken and the inner white fraction calculated. This is compared against a target saturation fraction - 0.01  (1% saturation) by default.

The integration time is increased or decreased proportionally to get closer to the target fraction, and the process repeated until within 5% of the target. For short integration times below 1/10th of a second this is trivial, but can be time consuming for longer captures, especially into the tens of seconds.

## References

IEC 2003 BS EN 61966-2-1:2000, IEC 61966-2-1:1999 “Multimedia systems and equipment -  Colour measurement and management: Colour management - Default RGB colour space - sRGB” Online: <https://bsol.bsigroup.com/Bibliographic/BibliographicInfoData/000000000030050324>
