import numpy as np
from PIL import Image
import math


ISO = "ISO"
DB = "DB"
 
def normalise_colours(image_array : np.ndarray) -> np.ndarray:
    """Normalises 8-bit RGB values (0-255) to non-linear sR'G'B' values (0-1)

    Args:
        image_array (np.array): numpy array of image pixels

    Returns:
        numpy.array: Non-linear sR'G'B array
    """    
    return  np.divide(image_array, 255)


def linearise_colours(image_array : np.ndarray) -> np.ndarray:
    """Converts non-linear sR'G'B' colour values to linear sRGB values using procedure defined in 
    IEC standard IEC 61966-2-1:1999/AMD1:2003 Section 5.2
    'Amendment 1 - Multimedia systems and equipment - Colour measurement and management - Part 2-1: Colour management - Default RGB colour space - sRGB'

    Args:
        image_array (np.array): numpy array of non-linear sR'G'B values

    Returns:
        numpy.array: Numpy array of linear sRGB values
    """
    cond1 = np.logical_and( -0.04045 <= image_array, image_array <= 0.04045)
    cond2 = image_array > 0.04045
    
    lin_array = np.zeros(image_array.shape)
    lin_array[cond1] = np.divide(image_array[cond1], 12.92)
    lin_array[cond2] = ((image_array[cond2]+0.055)/1.055)**2.4
    return lin_array




def lin_sRGB_to_XYZ(colour : list[float]|tuple[float]|np.ndarray) -> tuple[float]:
    """Converts linear sRGB values to CIE 1931 XYZ colour space values using procedure defined in 
    IEC standard IEC 61966-2-1:1999/AMD1:2003 Section 5.2
    'Amendment 1 - Multimedia systems and equipment - Colour measurement and management - Part 2-1: Colour management - Default RGB colour space - sRGB'


    Args:
        colour (list[float] | tuple[float] | np.ndarray): An iterable with three elements corresponding to 
        sRGB linear values in format ([R],[G],[B]).

    Returns:
        tuple[float]: A tuple containing the corresponding X, Y, and Z values in the CIE 1931 colourspace respectively
    """
    colour = np.array(colour)
    
    conversion_matrix = np.array([[0.4124, 0.3576, 0.1805],
                           [0.2126, 0.7152, 0.0722],
                           [0.0193, 0.1192, 0.9505]])
    xyz_matrix = np.multiply(colour, conversion_matrix)
    xyz=[]
    for channel in xyz_matrix:
        xyz.append(sum(channel))
    
    xyz = tuple(xyz)
    return xyz


def calc_relative_luminance(image : Image.Image | np.ndarray, mask: Image.Image|np.ndarray = None) -> float:
    """Calculate relative luminance of an image in Candela per Sq. Meter (cd/m^2)

    Args:
        image (Image.Image | np.ndarray): PIL Image (Must be in RGB8 mode) or Numpy array containing RGB pixel values.
    Returns:
        float: relative luminance of image
    """    
    """

    Args:
        image (Image.Image): 

    Returns:
        float: 
    """    
    #TODO: convert PIL mode to RGB8 regardless of existing mode
    image_array = np.array(image)
    norm_array = normalise_colours(image_array)

    lin_array = linearise_colours(norm_array)
    
    if mask is not None:
        mask_cond= np.array(mask) == 255
    else:
        mask_cond = np.full(image_array.shape[:-1], True)
            
    mean_lin = np.array([np.mean(channel[mask_cond]) for channel in lin_array.transpose(2,0,1)]) #Get mean for each linearised channel

    xyz = lin_sRGB_to_XYZ(mean_lin)
    relative_luminance = xyz[1]

    return relative_luminance




def calc_unscaled_absolute_luminance(image : Image.Image, integration_time : float, aperture : float,  speed : float, speed_format : str = ISO, mask:Image.Image=None, relative_luminance:float=None) -> float:
    """Calculate Unscaled Absolute Luminance
        Uses ISO2720:1974 procedure to calculate the unscaled absolute luminance of an image using the aperture, integration, and sensor speed
        Sensore speed may be in Gain or ISO format

    Args:
        image (Image.Image): PIL image to process
        integration_time (float): integration time in seconds
        aperture (float): f-number 
        speed (float): ISO or gain
        speed_format (str, optional): Whether the speed is counted in dB or ISO. Use luminance.ISO or luminance.DB or "ISO"/"DB" Defaults to ISO.

    Raises:
        ValueError: if speed_format is not equal to one of "ISO" or "DB"

    Returns:
        float: Unscaled Absolute Average Luminance
    """    
    speed_iso = None
    if speed_format not in [ISO, DB]:
        raise ValueError(f"Speed format not valid.\nGiven value: '{speed_format}' \nAccepted values: ['ISO'|'DB']")
    
    # Convert gain to ISO equivalent. NOTE: ISO is not a standard value between devices
    # and the lowest ISO ("Base ISO") which is often 100 on modern devices does not correspond
    # to a fixed physical quantity. A device specific 'calibration consant' K 
    # is used to standardise calibration when needed. 
    
    # i.e from ISO2720:1974 -   N^2 / t = ( L * S ) / K
    #where: N is f-number (aperture)
    #       t is integration time in seconds
    #       S is ISO
    #       L is relative luminance
    #       K is a reflected-light meter calibration constant
    
    # Gain as used in the IDS U3-3080CP-C-HQ Rev.2.2 camera 
    # for example also measures a similar quantity, but is measured in decibels (dB).
    # This conversion assumes that a gain of 1 (i.e no change to measured signal) corresponds to 100, 
    # and uses the amplitude ratio in decibels so that roughly an increase of 6dB corresponds to a doubling in ISO
    # i.e gain = 10 * log10((ISO / 100 )^2) 
    # and therefore ISO = 100 * 10^(gain / 20)
    
    if speed_format == DB:
        speed_iso = 100*(10**(speed/20))
    elif speed_format == ISO:
        speed_iso = speed
        
    if relative_luminance is None:
        relative_luminance = calc_relative_luminance(image, mask)
    
    # Using ISO2720:1974 - N^2 / t = ( L * S ) / K
    # ==> L / K = N^2 / (S * t)
    
    unscaled_absolute_luminance = relative_luminance*((aperture**2)/(speed_iso*integration_time))
    
    return unscaled_absolute_luminance
         
     
