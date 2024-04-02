from harvesters.core import Harvester
import os
import numpy as np

from cam_image import Cam_Image

PRODUCER_PATH = os.environ.get('PRODUCER_PATH')


class Camera:
    def __init__(self) -> None:
        h = Harvester() 
        
        #ADD produce file path
        h.add_file(PRODUCER_PATH)
        h.update()
        
        self.nodemap = h.create().remote_device.node_map

        #Set Pixel Format to BayerRG8 if available, else set to Mono8
        if "BayerRG8" in self._valid_pixel_formats():
            self.nodemap.PixelFormat.set_value("BayerRG8")
        else:
            self.nodemap.PixelFormat.set_value("Mono8")
    def capture_image(self):
        try:
            with self.nodemap.fetch_buffer() as buffer:
                image = buffer.payload.components[0].data
                
                image_array = np.array(image).reshape(buffer.payload.height, buffer.payload.width)
                
                return Cam_Image(image_array, )
        except:
            return None    

    def set_pixel_format(self, pixel_format):
        try:
            self.nodemap.PixelFormat.set_value(pixel_format)
            return True
        except:
            return False

    def _valid_pixel_formats(self):
        return self.nodemap.PixelFormat._get_symbolics()
    
    def _node_list(self):

        node_list = []
        for item in self.nodemap._get_nodes():
            try:
                node = item._get_node()
                node_tuple = (node._get_display_name(), item.to_string())
            except:
                node_tuple = (node._get_display_name(), None)
            finally:
                node_list.append(node_tuple)
        
        return node_list
    
    