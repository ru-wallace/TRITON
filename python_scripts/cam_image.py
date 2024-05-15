from PIL import Image, ImageDraw
from PIL.PngImagePlugin import PngInfo
import numpy as np
import traceback
from pathlib import Path
from datetime import datetime
import sys, os
import warnings
import math
warnings.filterwarnings("ignore", module=".*colour.*")

import colour_demosaicing

import luminance


class Resources:
     # Define constants for method names
    MENON_R = "menon_r"
    """
    Constant representing the Menon algorithm with refining step.
    """
    DDFAPD_R = "ddfapd_r"
    """
    Constant representing the DDFAPD algorithm with refining step.
    """
    MENON = "menon"
    """
    Constant representing the Menon algorithm without refining step.
    """
    DDFAPD = "ddfapd"
    """
    Constant representing the DDFAPD algorithm without refining step.
    """
    MALVAR = "malvar"
    """
    Constant representing the Malvar algorithm.
    """
    BILINEAR = "bilinear"
    """
    Constant representing the Bilinear interpolation algorithm.
    """
    AVERAGE_GREENS = "average_greens"
    """
    Constant representing the Average Greens method.
    """


class Cam_Image:
    
    def __init__(self, image:np.ndarray, timestamp:datetime, integration_time_us:int, auto:bool, gain:float, aperture:float, format:str, number:int=None, depth:float=None, pressure:float=None, cam_temp:float=None, environment_temp:float=None,  saturation_threshold:int=250, debayer_method:str = "average_greens", target_saturation_fraction:float=0.01, target_saturation_margin:float=0.005) -> None:
        """Create Cam_Image object which contains an Image and a combination of pre-set and calculated metadata.

        Args:
            image (np.ndarray): The image to be used
            timestamp (datetime): Timestamp
            integration_time (int): Integration time of image in microseconds
            gain (float): gain in dB
            depth (float): depth below surface when image was captured
            temp (float): Temperature of device when image was captured
        """        
        try:
            
            self._image = None
            self._image_array = None
            
            self._centre_mask = None
            self._outer_mask = None
            self._corner_mask = None
            self._concentric_masks = None
            
            self._inner_avgs = None
            self._outer_avgs = None
            self._corner_avgs = None
            
            self._inner_saturation_fraction = None
            self._outer_saturation_fraction = None
            self._corner_saturation_fraction = None
            
            
            self._correct_saturation=None
            
            self._relative_luminance = None
            self._unscaled_absolute_luminance = None
            
            
            self._number = None
            
            #remove extra empty dimensions
            image = image.squeeze().astype(np.uint8)
            
            self._original_image_array = image.copy()
            
            
            self.target_saturation_fraction = target_saturation_fraction
            self.target_saturation_margin = target_saturation_margin
            
            self.saturation_threshold = saturation_threshold
            
            #Debayer (demosaic) image using cv2 colour conversion function
            self.debayer_method = debayer_method
            
            self._format :str = format
            
            self._channels = ['R', 'G', 'B']
            
            if self._format != "BayerRG8":
                self._channels = None
                self._image_array = self.original_image_array.copy()
                #Assume image mode is L (greyscale) unless the format is BayerRG8
                self._image = Image.fromarray(self._image_array, mode="L")
            

            self._timestamp : datetime = timestamp

            self._integration_time_us : int = integration_time_us
            self._aperture : float = aperture
            self._auto : bool = auto
            
            self._gain : float = gain
            
            self._depth : float = depth
            
            self._pressure : float = pressure
            
            self._cam_temp :float = cam_temp
            
            self._environment_temp : float = environment_temp
            
        except Exception as e:
            traceback.print_exception(e)
            
    
    
    
    def _demosaic(self, method=Resources.AVERAGE_GREENS, pattern="RGGB"):    
        if self._image_array is not None:
            return
        self._image_array = self.original_image_array.copy()
        mode = "L"
        if self.format=="BayerRG8":
                    mode="RGB"
                    self._image_array : np.ndarray = debayer(self.original_image_array, method=method, pattern=pattern)
                    
        
        self._image : Image.Image = Image.fromarray(self._image_array, mode=mode)

    def _create_masks(self):
        if self._image is None:
            self._demosaic()
            
        #temporary values for active area of camera hardcoded in now
        #TODO load in from json or similar
        
        reduced_centre = [613, 517]
        reduced_radius =  236
        
        
        full_size_centre = [coord * 2 for coord in reduced_centre]
        full_size_radius = reduced_radius * 2
        
        
        centre = full_size_centre
        radius = full_size_radius
        margin = 100
        
        if sum(self._original_image_array.shape) > sum(self._image_array.shape):
            centre = reduced_centre
            radius = reduced_radius
            margin = 50

        

        #print(f"Creating Mask: image_array: {self.image_array.shape} original_image_array: {self.original_image_array.shape}, format: {self.format}, centre: {centre}, radius:{radius}", file=sys.stderr)
        #Generate a mask which will hide the area outside this circle.
        #Function was designed for a fisheye lens so this is the sensor active area for that
        self._centre_mask = create_circle_mask(self._image_array, centre=centre, radius=radius)
        
        #Generate a mask which will hide the centre circle, plus a margin to avoid the majority of light bleed
        self._outer_mask = create_circle_mask(self._image_array, centre=centre, radius=[radius+margin, 5000])

        #Create mask which hides everything but the corners of the image
        self._corner_mask = create_corner_mask(self._image_array, radius=2*margin)
        
        
        #Create a set of ring masks of the margin size, expanding out from the inner circle to the edge
        diagonal_radius = int(0.5*math.sqrt(self._image_array.shape[0]**2 + self._image_array.shape[1]**2))
        rad = radius
        radii = {}
        while rad <= diagonal_radius:
            radii[f"radius_{rad}-{rad+margin}"] =[rad, rad + margin]
            rad += margin
        
        
        self._concentric_masks = {}
        for name, rad_set in radii.items():
            self._concentric_masks[name] = create_circle_mask(self._image_array, centre=centre, radius=rad_set)
    

    def _calculate_luminance(self)-> None:
        if self._centre_mask is None:
            self._create_masks()
        
        #Change integration time from microseconds to seconds
        integration_sec = self.integration_time_us/10e6

        #If the image is monochrome, the image pixels are just relative luminance scaled to 255 so can use this if we apply a mask.
        #If RGB, we use the IEC process as implemented in the luminance module to calculate relative luminance.        
        if self.format == "Mono8":
            self._relative_luminance = np.divide(get_pixel_averages_for_channels(self._image, mask=self._centre_mask, saturation_threshold=self.saturation_threshold), 255)[0]
            
        else:
            self._relative_luminance = luminance.calc_relative_luminance(self._image_array, mask=self._centre_mask, saturation_threshold=self.saturation_threshold)
            
            
        #Calculate the unscaled absolute luminance using the IEC defined process.
        self._unscaled_absolute_luminance:float = luminance.calc_unscaled_absolute_luminance(aperture=self.aperture,
                                                                            integration_time=integration_sec,
                                                                            speed= self.gain,
                                                                            speed_format=luminance.DB,
                                                                            relative_luminance=self._relative_luminance
                                                                            )
        
        
        
    def _get_saturation_fractions(self) -> None:
        if self._centre_mask is None:
            self._create_masks()
        #Calculate the fraction of pixels saturated in the active circle
        self._inner_saturation_fraction = get_fraction_saturated_pixels(self._image, mask=self._centre_mask, saturation_threshold=self.saturation_threshold)
        
        #Calculate the fraction of pixels saturated in the outer dark area
        self._outer_saturation_fraction = get_fraction_saturated_pixels(self._image, mask=self._outer_mask, saturation_threshold=self.saturation_threshold)

        #Calculate the fraction of pixels saturated in the corners
        self._corner_saturation_fraction = get_fraction_saturated_pixels(self._image_array, mask=self._corner_mask, saturation_threshold=self.saturation_threshold)

        
        self._concentric_saturation_fractions = {}
        for name, mask in list(self._concentric_masks.items()):
            self._concentric_saturation_fractions[f"concentric_saturation_fraction_{name}"] = get_fraction_saturated_pixels(self._image_array, mask=mask, saturation_threshold=self.saturation_threshold)
    
    def _get_pixel_averages(self) -> None:
        if self._centre_mask is None:
            self._create_masks()
        #Calculate the average pixel value for each channel  in the active circle
        self._inner_avgs :tuple[float]= get_pixel_averages_for_channels(self._image, mask=self._centre_mask)
        
        #Calculate the average pixel value for each channel in the outer dark area
        self._outer_avgs:tuple[float] = get_pixel_averages_for_channels(self._image, mask=self._outer_mask)

        #Calculate the average pixel value for each channel in the corners
        self._corner_avgs: tuple[float]= get_pixel_averages_for_channels(self._image_array, mask=self._corner_mask)
            
        #Getter and setter functions  
    
    
    
    @property
    def original_image_array(self) -> np.ndarray:
        return self._original_image_array
    
    @property
    def image(self) -> Image.Image:
        if self._image is None:
            self._demosaic(method=Resources.AVERAGE_GREENS, pattern="RGGB")
        return self._image
            
    
    @property
    def image_array(self) -> np.ndarray:
        if self._image_array is None:
            self._demosaic(method=Resources.AVERAGE_GREENS, pattern="RGGB")
        return self._image_array
    
    @property
    def format(self) -> str:
        return self._format
    
    @property
    def timestamp(self) -> datetime:
        return self._timestamp
    
    @property
    def number(self) -> str:
        return self._number
    
    @property
    def integration_time_us(self) -> int:
        return self._integration_time_us
    
    @property
    def aperture(self) -> float:
        return self._aperture
    
    @property
    def auto(self) -> bool:
        return self._auto
    @property
    def gain(self) -> float:
        return self._gain
    
    @property
    def depth(self) -> float:
        return self._depth
    
    @property
    def pressure(self) -> float:
        return self._pressure
    
    @property
    def cam_temp(self) -> float:
        return self._cam_temp
    
    @property
    def environment_temp(self) -> float:
        return self._environment_temp

    
    @property
    def relative_luminance(self) -> float:
        if self._relative_luminance is None:
            self._calculate_luminance()        
        return self._relative_luminance
    
    @property
    def absolute_luminance(self) -> float:
        if self._unscaled_absolute_luminance is None:
            self._calculate_luminance()
        return self._unscaled_absolute_luminance
    
    @property
    def inner_avgs(self) -> tuple[float]:
        if self._inner_avgs is None:
            self._get_pixel_averages()
        return self._inner_avgs
    
    @property
    def inner_saturation_fraction(self) -> float:
        if self._inner_saturation_fraction is None:
            self._get_saturation_fractions()
        return self._inner_saturation_fraction    
    
    @property
    def outer_avgs(self) -> tuple[float]:
        if self._outer_avgs is None:
            self._get_pixel_averages()
        return self._outer_avgs
    
    @property
    def outer_saturation_fraction(self) -> float:
        if self._outer_saturation_fraction is None:
            self._get_saturation_fractions()        
        return self._outer_saturation_fraction

    @property
    def corner_avgs(self) -> tuple[float]:
        if self._corner_avgs is None:
            self._get_pixel_averages()
        return self._corner_avgs
    
    @property
    def corner_saturation_fraction(self) -> float:
        if  self._corner_saturation_fraction is None:
            self._get_saturation_fractions()
        return self._corner_saturation_fraction
    
    @property
    def concentric_saturation_fractions(self) -> dict:
        if self._concentric_saturation_fractions is None:
            self._get_saturation_fractions()
        return self._concentric_saturation_fractions
    
    @property
    def correct_saturation(self):
        if self._inner_saturation_fraction is None:
            self._get_saturation_fractions()
        self._correct_saturation = abs(self.inner_saturation_fraction - self.target_saturation_fraction) < self.target_saturation_margin
        return self._correct_saturation
    @property
    def info(self)->dict:
        
        info = {"number" : self.number,
                "time" : self.time_string('%Y-%m-%d %H:%M:%S.%f')[:-3],
                "integration_microseconds" : self.integration_time_us,
                "integration_seconds": self.integration_time_us/1000000,
                "auto": self.auto,
                "gain_dB" : self.gain,
                "depth_m" : self.depth,
                "pressure_mB" : self.pressure,
                "device temp_°C": self.cam_temp,
                "sensor_temp_°C": self.environment_temp,
                "format": self.format,
                "correct_saturation" : self.correct_saturation,
                "inner_saturation_fraction": self.inner_saturation_fraction,
                "outer_saturation_fraction": self.outer_saturation_fraction,
                "corner_saturation_fraction": self.corner_saturation_fraction,
                "relative luminance": self.relative_luminance,
                "absolute_luminance": self.absolute_luminance
                }
        
        info.update(self.add_channels("inner_pixel_averages", self.inner_avgs))
        info.update(self.add_channels("outer_pixel_averages", self.outer_avgs))
        info.update(self.add_channels("corner_pixel_averages", self.corner_avgs))
        info.update(self.concentric_saturation_fractions)
        
        return info

    def add_channels(self, name, values:list):
        new_dict = {}
        if self._channels is not None:
            for i, value in enumerate(values):
                new_dict[f"{name}_{self._channels[i]}"] = value
        else:
            new_dict[f"{name}"] = values[0]
            
        return new_dict

    def set_number(self, number:int):
        self._number = number
    
    def set_auto(self, auto:bool)->None:
        self._auto = auto

    def set_depth(self, depth_m: float)->None:
        self._depth = depth_m

    def set_pressure(self, pressure_mb: float)->None:
        self._pressure = pressure_mb
        
    def set_environment_temperature(self, temp_C: float)->None:
        self._environment_temp = temp_C

    def time_string(self, format:str="%Y_%m_%d__%H_%M_%S") -> str:
        """Generate string of the timestamp. Uses a default format unelss specified
            Uses datetime.strftime() function and formats.
        Args:
            format (str, optional): String format to output timestamp in. Defaults to "%Y_%m_%d__%H_%M_%S".

        Returns:
            str: String representation of time, by default in YYYY_mm_dd__HH_MM_SS format.
        """        
        return datetime.strftime(self._timestamp, format)
    
    def metadata(self, additional_items:dict=None) -> PngInfo:
        """Calls create_metadata function to generate png metadata
        for use when saving.

        Returns:
            PngInfo: Png Metadata object with image metadata
        """        
        return create_metadata(self, additional_items=additional_items)
    
    def show(self) -> None:
        """Show Image in default system image program.
        Does not work when in ssh mode (Unless you do some fiddly stuff).
        """        
        try:
            self.image.show()
        except Exception as e:
            traceback.print_exception(e) 
            
    def save(self, path:str|Path, additional_metadata:dict=None) -> bool:
        """Save: Save Image using PIL Image.Image.save() function. Also saves image
        metadata and any additional metadata fields specified in {"key":"value"} dict format

        Args:
            path (str | Path): filepath to save image to
            additional_metadata (dict, optional): Additional metadata to add to image. Defaults to None.

        Returns:
            bool: True if saving is successful, False otherwise
        """        

            
        metadata = self.metadata(additional_items=additional_metadata)
        
        
        if isinstance(path, str):
            try:
                path = Path(path)
            except:
                print("Saving unsuccessful: unable to resolve file path")
                return False
        self.image.save(path, pnginfo=metadata)
        return True

            
#functions
        
def debayer_average_greens_method(image: np.ndarray, pattern:str) -> np.ndarray:
    """
    Debayers a Bayer pattern image using the average greens method.
    This reduces the resolution of the image by half in each dimension.

    Args:
        image (np.ndarray): The input Bayer pattern image.

    Returns:
        np.ndarray: The debayered RGB image array.
    """
    
    red_mask, green_mask_1, blue_mask = colour_demosaicing.masks_CFA_Bayer(image.shape, pattern=pattern)
    green_mask_2 = green_mask_1.copy()
    green_mask_1[0::2] = 0
    green_mask_2[1::2] = 0

    ncols = sum(red_mask[0])
    
    red = image[red_mask].reshape((-1, ncols))
    green1 = image[green_mask_1].reshape((-1, ncols))
    green2 = image[green_mask_2].reshape((-1, ncols))
    blue = image[blue_mask].reshape((-1, ncols))
    
    green_avg = np.mean(np.array([green1, green2]), axis=0)
    
    # Create the RGB image array
    rgb_array = np.dstack((red, green_avg, blue))
    
    return rgb_array

        
def debayer(image:np.ndarray, method="average_greens", pattern="RGGB")-> np.ndarray:
    """## Debayer or Demosaic an Image.
    
    ### Possible methods: 
        "menon"/"ddfapd": Demosaicing With Directional Filtering and a posteriori Decision (Menon 2007)
        
                            To use the Menon algorithm with the refining step, use "menon_r" or "ddafdp_r"
        
        "malvar":Malvar (2004) demosaicing algorithm
        
        "bilinear": bilinear interpolation
        
    Args:
        image (np.ndarray): Image Bayer array
        method (str, optional): Debayering method. Defaults "menon"
        pattern (str, optional): Image Pattern: 
    Returns:
        np.ndarray: De-bayered RGB image array of shape (width, height, 3)
    """    
    
    start=datetime.now()
    
    bayer_array = image.astype(np.uint8)/255
    
    debayered_array = None
    

   

    # Debayering method switch case
    match method:
        # Menon Algorithm
        case Resources.MENON_R: 
            debayered_array = colour_demosaicing.demosaicing_CFA_Bayer_Menon2007(CFA=bayer_array, pattern=pattern)
        case Resources.DDFAPD_R:
            debayered_array = colour_demosaicing.demosaicing_CFA_Bayer_Menon2007(CFA=bayer_array, pattern=pattern)
        case Resources.MENON: 
            debayered_array = colour_demosaicing.demosaicing_CFA_Bayer_Menon2007(CFA=bayer_array, pattern=pattern, refining_step=False)
        case Resources.DDFAPD:
            debayered_array = colour_demosaicing.demosaicing_CFA_Bayer_Menon2007(CFA=bayer_array, pattern=pattern, refining_step=False)
        # Malvar Algorithm
        case Resources.MALVAR:
            debayered_array = colour_demosaicing.demosaicing_CFA_Bayer_Malvar2004(CFA=bayer_array, pattern=pattern)
        # Bilinear Interpolation    
        case Resources.BILINEAR:
            debayered_array = colour_demosaicing.demosaicing_CFA_Bayer_bilinear(CFA=bayer_array, pattern=pattern)
        case Resources.AVERAGE_GREENS:
            debayered_array = debayer_average_greens_method(bayer_array, pattern=pattern)
    

    #Normalise to between 0 and 255
    normalised_array = (debayered_array / np.max(debayered_array)) * 255    
    
    #Convert back to np.array and set type to uint8 to play nicely with PIL
    rgb_array = np.array(normalised_array).astype(np.uint8)
    #print(f"Debayering Time with method {method}:")
    #print(f"Image size before: {image.shape} - Image size after: {rgb_array.shape}")
    print(datetime.now()-start)
    return rgb_array

def create_metadata(image:Cam_Image, additional_items:dict=None) ->PngInfo: 
    """Create Metadata
    Create a set of metadata containing all the Cam_Image info to add to a file when saving
    Args:
        image (Cam_Image): _description_

    Returns:
        PngInfo: _description_
    """    
    try:
        metadata = PngInfo()
        for key, value in image.info.items():
            key = key.strip().replace(" ", "_")
            metadata.add_text(key, str(value))      
                  
        if additional_items:
            for key, value in additional_items.items():
                key = key.strip().replace(" ", "_")
                metadata.add_text(key, str(value))   
            
        return metadata
       
    except Exception as e:
        traceback.print_exception(e)     
        
        
def get_fraction_saturated_pixels(image: Image.Image, mask: Image.Image = None, invert_mask:bool=False, saturation_threshold:int=255) -> float:
  
    """Find the fraction of pixels which have a value greater than the threshold. Threshold is 250 by default.

    Args:
        image (Image.Image): Image to process
        mask (Image.Image, optional): Mask to cover image. Must be a PIL Image of mode "L" where ignored areas
        are value 0 and active areas are value 255. Defaults to None.
        invert_mask (bool, optional): option to invert mask so only dark areas are considered. Defaults to False.
        threshold (int, optional): Threshold value above which pixels are counted as saturated. Defaults to 250.

    Returns:
        float: Fraction of pixels which are saturated.
    """    
    try: 
        
        
        image_array = np.array(image)
        
        mask_bool = np.full(image_array.shape, True)
          
        if mask is not None:
            mask_image_array = np.array(mask)
            mask_bool = mask_image_array > 100
        
        
        if invert_mask:
                mask_bool  = np.invert(mask_bool) 

        
        masked_array = image_array[mask_bool]
                
        total_pixels = masked_array.size
        
        number_saturated  = np.size(masked_array[masked_array > saturation_threshold])

        fraction_saturated = number_saturated/total_pixels
        

        
        
        return fraction_saturated
    except IndexError as e:
        print("Error: ", file=sys.stderr)
        print(f"image_array shape: {image_array.shape}", file=sys.stderr)
        print(f"image_array size: {image_array.size}", file=sys.stderr)
        print(f"mask_bool shape: {mask_bool.shape}", file=sys.stderr)
        print(f"masked_array size: {mask_bool.size}", file=sys.stderr)
        traceback.print_exception(e)
    except Exception as e:
        traceback.print_exception(e)
            
def get_pixel_averages_for_channels(image:Image.Image, mask:Image.Image=None, invert_mask:bool = False, saturation_threshold:int=255) ->tuple[float]:
    """Calculate the average pixel value for each channel. If a mask if provided, calculates for only active area.

    Args:
        image (Image.Image): Image to process.
        mask (Image.Image, optional): Mask to limit areas. PIL Image of mode "L" with pixel values of 0 to ignore and 255 to include. Defaults to None.
        invert_mask (bool, optional): Option to invert mask and ignore pixel values of 255 and include values of 0. Defaults to False.

    Returns:
        tuple[float]: Average pixel value for each channel. Usually 8-bit depending on mode so 0-255
    """    
    
    image_array = np.array(image)
    

    mask_bool = np.full(image_array.shape, True)
    
    #Numpy masked arrays use masks where True is masked and False is not
    if mask is not None:
        mask_bool = np.array(mask) == 0
        
    if  invert_mask:
        mask_bool = np.invert(mask_bool)
    

    if len(image_array.shape) == 2:
        image_array = np.expand_dims(image_array, axis=2)
    
    masked_array = np.ma.array(image_array, mask=mask_bool)
    
    means = masked_array.mean(axis=(0,1))

    return tuple(means)

    
def create_circle_mask(image:np.ndarray, centre:tuple, radius:int|list) -> Image.Image:
    """Create a mask image. Dark outside and white
    circle with defined centre and radius.

    Args:
        image (np.ndarray): Image to be masked
        centre (tuple): The centre of the circle. For a fisheye lense the active area will likely be close but not exactly the image centre
        radius (int|list): Radius of the circle to draw. If multiple values are given, they must be in pairs, i.e [[10, 50], [70,90]]. The smaller value of each
        pair will be the inner radius of a white band, and the larger will be the outer radius.
        

    Returns:
        Image: Image mask of same shape as  image passed in with a white circle on black background
    """ 
    
    x,y = centre
    
    try:
        initial_radius = radius
        if isinstance(radius, list):
            if not isinstance(radius[0], list):
                radius = [radius,]
            
            radius.sort(key=lambda x: x[1], reverse=True)
        else:
            radius = [[0, radius],]
        
        height, width = image.shape[0:2]
        mode = "L"
        if len(image.shape) > 2:
            mode = "RGB"
        
        mask = Image.new(mode=mode, size=(width, height), color='black')
        draw = ImageDraw.Draw(mask)
        
        for band in radius:
            
            r_white_circle = max(band)
            r_black_circle = min(band)

            w_left = x-r_white_circle
            w_right = x+r_white_circle
            w_top = y-r_white_circle
            w_bottom = y+r_white_circle
            
            draw.ellipse((w_left, w_top, w_right, w_bottom), fill='white')
            
            if r_black_circle > 1:
                b_left = x-r_black_circle
                b_right = x+r_black_circle
                b_top = y-r_black_circle
                b_bottom = y+r_black_circle
                
                draw.ellipse((b_left, b_top, b_right, b_bottom), fill='black')
   
        return mask

    except Exception as e:
        print("Initial Radius: ", initial_radius, file=sys.stderr)
        print("Radius: ", radius, file=sys.stderr)
        traceback.print_exception(e, file=sys.stderr)
        raise Exception("AAAgggh")
    

def create_corner_mask(image:np.ndarray, radius:int)->Image.Image:
    """Create a mask image for the passed in image with a circle of the set radius
    centred on each corner.

    Args:
        image (Image): Image to be masked
        radius (int): Radius of desired corner circles

    Returns:
        Image: Mask image of same size as passed-in image. Black background with white corner circles
    """    

    height, width = image.shape[0:2]
    mode = "L"
    if len(image.shape) > 2:
        mode = "RGB"
    
    # Create a new black image of the same size
    mask = Image.new(mode=mode, size=(width, height), color='black')
    
    # Draw circles on the new image at each corner
    draw = ImageDraw.Draw(mask)
  
    
    # Top-left corner
    draw.ellipse((-radius, -radius, radius, radius), fill="white")
    
    # Top-right corner
    draw.ellipse((width - radius, -radius, width + radius, radius), fill="white")
    
    # Bottom-left corner
    draw.ellipse((-radius, height - radius, radius, height + radius), fill="white")
    
    # Bottom-right corner
    draw.ellipse((width - radius, height - radius, width + radius, height + radius), fill="white")
    

    return mask

