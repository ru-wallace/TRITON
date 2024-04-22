from PIL import Image, ImageDraw
from PIL.PngImagePlugin import PngInfo
import numpy as np
import traceback
from pathlib import Path
from datetime import datetime

import warnings
warnings.filterwarnings("ignore", module=".*colour.*")

import colour_demosaicing

import luminance


class Cam_Image:
    
    def __init__(self, image:np.ndarray, timestamp:datetime, integration_time:int, auto:bool, gain:float, depth:float, cam_temp:float, sensor_temp:float, format:str) -> None:
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
            #remove extra empty dimensions
            image = image.squeeze().astype(np.uint8)
            
            #Assume image mode is L (greyscale) unless the format is BayerRG8
            mode="L"
            
            
            processed_colour_image = image
            #Debayer (demosaic) image using cv2 colour conversion function
            if format=="BayerRG8":
                mode="RGB"
                processed_colour_image = debayer(image, method="menon", pattern="RGGB")
            
            
            
            self._image : Image.Image = Image.fromarray(processed_colour_image, mode=mode)
            
            self._format :str = format
            
            self._timestamp : datetime = timestamp

            self._integration_time : int = integration_time
            
            self._auto : bool = auto
            
            self._gain : float = gain
            
            self._depth : float = depth
            
            self._cam_temp :float = cam_temp
            
            self._sensor_temp : float = sensor_temp
            

            
            #temporary values for active area of camera hardcoded in now
            #TODO load in from json or similar
            centre = [1226, 1034]
            radius = 472
            
            
            #Generate a mask which will hide the area outside this circle.
            #Function was designed for a fisheye lens so this is the sensor active area for that
            centre_mask = create_centre_mask(image, centre=centre, radius=radius)
            

            
            #Change integrateion time from microseconds to seconds
            integration_sec = integration_time/1000000
            
            
            
            
            
            self._relative_luminance = None  
            
            #If the image is monochrome, the image pixels are just relative luminance scaled to 255 so can use this if we apply a mask.
            #If RGB, we use the IEC process as implemented in the luminance module to calculate relative luminance.        
            if format == "Mono8":
                self._relative_luminance = get_average_for_channels(self._image, mask=centre_mask)[0]/255
            else:
                self._relative_luminance = luminance.calc_relative_luminance(self._image, mask=centre_mask)
                
                
            #Calculate the unscaled absolute luminance using the IEC defined process.
            
            self._unscaled_absolute_luminance:float = luminance.calc_unscaled_absolute_luminance(self._image, 
                                                                                mask=centre_mask,
                                                                                aperture=1,
                                                                                integration_time=integration_sec,
                                                                                speed= gain,
                                                                                speed_format=luminance.DB,
                                                                                relative_luminance=self._relative_luminance
                                                                                )
            
            #Calculate the average pixel value for each channel and fraction of all pixels saturated in the active circle
            self._inner_fraction_white = get_fraction_white_pixels(image, mask=centre_mask)
            self._inner_avgs :tuple[float]= get_average_for_channels(self._image, mask=centre_mask)
            
            #Generate a mask which will hide the centre circle, plus a margin to avoid the majority of light bleed
            outer_mask = create_centre_mask(image, centre=centre, radius=radius+100)
            
            #Calculate the average pixel value for each channel and fraction of all pixels saturated in the outer dark area
            self._outer_fraction_white = get_fraction_white_pixels(image, mask=outer_mask, invert_mask = True)
            self._outer_avgs:tuple[float] = get_average_for_channels(self._image, mask=outer_mask, invert_mask = True)
            
            
            #Create mask which hides everything but the corners of the image
            corner_mask = create_corner_mask(image=image, radius=200)
            
            #Calculate the average pixel value for each channel and fraction of all pixels saturated in the corners
            self._corner_avgs: tuple[float]= get_average_for_channels(self._image, mask=corner_mask)
            self._corner_fraction_white = get_fraction_white_pixels(image, mask=corner_mask)
            
        except Exception as e:
            traceback.print_exc(e)
            
    #Getter and setter functions  
        
    @property
    def image(self) -> Image.Image:
        return self._image
    
    @property
    def format(self) -> str:
        return self._format
    
    @property
    def timestamp(self) -> datetime:
        return self._timestamp
    
    @property
    def integration_time(self) -> int:
        return self._integration_time
    
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
    def cam_temp(self) -> float:
        return self._cam_temp
    
    @property
    def sensor_temp(self) -> float:
        return self._sensor_temp

    
    @property
    def relative_luminance(self) -> float:
        return self._relative_luminance
    
    @property
    def unscaled_absolute_luminance(self) -> float:
        return self._unscaled_absolute_luminance
    
    @property
    def inner_avgs(self) -> tuple[float]:
        return self._inner_avgs
    
    @property
    def inner_fraction_white(self) -> float:
        return self._inner_fraction_white    
    
    @property
    def outer_avgs(self) -> tuple[float]:
        return self._outer_avgs
    
    @property
    def outer_fraction_white(self) -> float:
        return self._outer_fraction_white

    @property
    def corner_avgs(self) -> tuple[float]:
        return self._corner_avgs
    
    @property
    def corner_fraction_white(self) -> float:
        return self._corner_fraction_white


    def set_depth(self, depth_m: float)->None:
        self._depth = depth_m

    def time_string(self, format:str="%Y_%m_%d__%H_%M_%S") -> str:
        """Generate string of the timestamp. Uses a default format unelss specified
            Uses datetime.strftime() function and formats.
        Args:
            format (str, optional): String format to output timestamp in. Defaults to "%Y_%m_%d__%H_%M_%S".

        Returns:
            str: String representation of time, by default in YYYY_mm_dd__HH_MM_SS format.
        """        
        return datetime.strftime(self._timestamp, format)
    
    def metadata(self) -> PngInfo:
        """Calls create_metadata function to generate png metadata
        for use when saving.

        Returns:
            PngInfo: Png Metadata object with image metadata
        """        
        return create_metadata(self)
    
    def show(self) -> None:
        """Show Image in default system image program.
        Does not work when in ssh mode (Unless you do some fiddly stuff).
        """        
        try:
            self.image.show()
        except Exception as e:
            traceback.print_exc(e) 
            
    def save(self, path:str|Path, additional_metadata:dict=None) -> bool:
        """Save: Save Image using PIL Image.Image.save() function. Also saves image
        metadata and any additional metadata fields specified in {"key":"value"} dict format

        Args:
            path (str | Path): filepath to save image to
            additional_metadata (dict, optional): Additional metadata to add to image. Defaults to None.

        Returns:
            bool: True if saving is successful, False otherwise
        """        
        try:
            
            metadata = self.metadata()
            
            if additional_metadata is not None: 
                for key, value in additional_metadata.items():
                    metadata.add_text(key, value)
            
            if isinstance(path, str):
                try:
                    path = Path(path)
                except:
                    print("Saving unsuccessful: unable to resolve file path")
                    return False
            self.image.save(path, pnginfo=metadata)
            return True
        except Exception as e:
            print("Unable to Save Image")
            traceback.print_exc(e)
            return False
            
            
#functions
        

        
def debayer(image:np.ndarray, method="menon", pattern="RGGB")-> np.ndarray:
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
    

    
    match method:
        #Menon Algorithm
        case "menon_r": 
            debayered_array = colour_demosaicing.demosaicing_CFA_Bayer_Menon2007(CFA=bayer_array, pattern=pattern)
        case "ddfapd_r":
            debayered_array = colour_demosaicing.demosaicing_CFA_Bayer_Menon2007(CFA=bayer_array, pattern=pattern)
        case "menon": 
            debayered_array = colour_demosaicing.demosaicing_CFA_Bayer_Menon2007(CFA=bayer_array, pattern=pattern, refining_step=False)
        case "ddfapd":
            debayered_array = colour_demosaicing.demosaicing_CFA_Bayer_Menon2007(CFA=bayer_array, pattern=pattern, refining_step=False)
        #Malvar Algorithm
        case "malvar":
            debayered_array = colour_demosaicing.demosaicing_CFA_Bayer_Malvar2004(CFA=bayer_array, pattern=pattern)
        #Bilinear Interpolation    
        case "bilinear":
            debayered_array = colour_demosaicing.demosaicing_CFA_Bayer_bilinear(CFA=bayer_array, pattern=pattern)

    #Normalise to between 0 and 255
    normalised_array = (debayered_array / np.max(debayered_array)) * 255    
    
    #Convert back to np.array and set type to uint8 to play nicely with PIL
    rgb_array = np.array(normalised_array).astype(np.uint8)
    print(f"Debayering Time with method {method}:")
    print(datetime.now()-start)
    return rgb_array

def create_metadata(image:Cam_Image) ->PngInfo: 
    """Create Metadata
    Create a set of metadata containing all the Cam_Image info to add to a file when saving
    Args:
        image (Cam_Image): _description_

    Returns:
        PngInfo: _description_
    """    
    try:
        metadata = PngInfo()
        metadata.add_text("timestamp", image.time_string())
        metadata.add_text("format", image.format)
        metadata.add_text("integration", str(image.integration_time))
        metadata.add_text("gain", str(image.gain))
        metadata.add_text("depth", str(image.depth))
        metadata.add_text("temp", str(image.cam_temp))
        metadata.add_text("relative_lum", str(image.relative_luminance))
        metadata.add_text("unscaled_abs_lum", str(image.unscaled_absolute_luminance))
        metadata.add_text("pixel_avgs_inner", str(image.inner_avgs))
        metadata.add_text("white_fraction_inner", str(image.inner_fraction_white))
        metadata.add_text("pixel_avgs_outer", str(image.outer_avgs))
        metadata.add_text("white_fraction_outer", str(image.outer_fraction_white))
        metadata.add_text("pixel_avgs_corners", str(image.corner_avgs))
        metadata.add_text("white_fraction_corner", str(image.corner_fraction_white))             
        
        return metadata
       
    except Exception as e:
        traceback.print_exc(e)     
        
        
def get_fraction_white_pixels(image: np.ndarray, mask: Image.Image = None, invert_mask:bool=False, threshold:int=250) -> float:
  
    """Find the fraction of pixels which have a value greater than the threshold. Threshold is 250 by default.

    Args:
        image (np.ndarray): Image array to process
        mask (Image.Image, optional): Mask to cover image. Must be a PIL Image of mode "L" where ignored areas
        are value 0 and active areas are value 255. Defaults to None.
        invert_mask (bool, optional): option to invert mask so only dark areas are considered. Defaults to False.
        threshold (int, optional): Threshold value above which pixels are counted as saturated. Defaults to 250.

    Returns:
        float: Fraction of pixels which are saturated.
    """    
    try: 
        
        number_white = 0
        
        


        if mask is not None:
            mask_cond = np.array(mask) == 255
            if invert_mask:
                mask_cond  = np.invert(mask_cond)
            image = image[mask_cond]
            
        total_pixels = image.size
        
        number_white += np.count_nonzero(image > threshold) #create boolean array that is true when average of colour values is greater than 250

        fraction_white = number_white/total_pixels
        return fraction_white
    
    except Exception as e:
        traceback.print_exception(e)
            
def get_average_for_channels(image:Image.Image, mask:Image.Image=None, invert_mask:bool = False) ->tuple[float]:
    """Calculate the average pixel value for each channel. If a mask if provided, calculates for only active area.

    Args:
        image (Image.Image): Image to process.
        mask (Image.Image, optional): Mask to limit areas. PIL Image of mode "L" with pixel values of 0 to ignore and 255 to include. Defaults to None.
        invert_mask (bool, optional): Option to invert mask and ignore pixel values of 255 and include values of 0. Defaults to False.

    Returns:
        tuple[float]: Average pixel value for each channel. Usually 8-bit depending on mode so 0-255
    """    
    if image.mode not in ["RGB", "L"]:
        print("Image mode must be 'RGB' or 'L'")
        print("Mode of passed image: ", image.mode)
        return (None, None, None)
    
    if mask is None:
        mask = np.full(image.size, True)
    else:
        mask = np.array(mask) == 255
        
        if invert_mask:
            mask  = np.invert(mask)
    
    mean_value = []
    for channel in image.split():
        channel_array = np.array(channel)
        channel_mean = np.mean(channel_array[mask])
        mean_value.append(round(channel_mean, 3))
    
    return tuple(mean_value)
    
    
def create_centre_mask(image:np.ndarray, centre:tuple, radius:int) -> Image:
    """Create a mask image. Dark outside and white
    circle with defined centre and radius.

    Args:
        image (Image): Image to be masked
        centre (tuple): The centre of the circle. For a fisheye lense the active area will likely be close but not exactly the image centre
        radius (int): Radius of the circle to draw

    Returns:
        Image: Image mask of same shape as  image passed in with a white circle on black background
    """    
    
    height, width = image.shape
    mask = Image.new('L', (width, height), 0)
    draw = ImageDraw.Draw(mask)
    x,y = centre
    left = x-radius
    right = x+radius
    top = y-radius
    bottom = y+radius
    
    draw.ellipse((left, top, right, bottom), fill=255)

    return mask
    

def create_corner_mask(image:np.ndarray, radius:int)->Image:
    """Create a mask image for the passed in image with a circle of the set radius
    centred on each corner.

    Args:
        image (Image): Image to be masked
        radius (int): Radius of desired corner circles

    Returns:
        Image: Mask image of same size as passed-in image. Black background with white corner circles
    """    
    # Get the size of the original image
    height, width = image.shape
    
    # Create a new black image of the same size
    mask = Image.new("L", (width, height), color="black")
    
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

