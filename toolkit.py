import os
import numpy as np
import rawpy
from astropy.io import fits
from typing import Dict, Any, List, Optional, Callable

class AstroPreprocessor:
    """
    A toolkit for ingesting and standardizing astrophotography image files.
    Handles RAW to FITS conversion while preserving linear sensor data.
    """
    
    def __init__(self, output_dir="output"):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
            except Exception as e:
                print(f"Error creating output directory: {e}")

    def load_fits(self, file_path: str):
        """
        Reads a standard FITS file and returns the header and image data array.
        """
        print(f"Loading FITS: {file_path}")
        try:
            with fits.open(file_path) as hdul:
                # Astrophotography data is usually in the Primary HDU
                # but we check if primary is empty (only header)
                idx = 0
                while idx < len(hdul) and hdul[idx].data is None:
                    idx += 1
                
                if idx < len(hdul):
                    data = hdul[idx].data
                    header = hdul[idx].header
                    return data, header
                else:
                    return None, hdul[0].header
        except Exception as e:
            print(f"Error loading FITS {file_path}: {e}")
            return None, None

    def get_fits_info(self, file_path: str) -> Dict[str, Any]:
        """Returns header cards and image shape for display."""
        data, header = self.load_fits(file_path)
        if header is None:
            return {}
        
        info = {
            "cards": {k: (v, header.comments[k]) for k in header.keys() if k},
            "shape": data.shape if data is not None else "No data",
            "dtype": str(data.dtype) if data is not None else "N/A"
        }
        return info

    def edit_fits_header(self, file_path: str, updates: Dict[str, Any]):
        """Updates specific header cards in a FITS file."""
        try:
            with fits.open(file_path, mode='update') as hdul:
                header = hdul[0].header
                for key, value in updates.items():
                    header[key] = value
                hdul.flush()
            return True
        except Exception as e:
            print(f"Error updating header of {file_path}: {e}")
            return False

    def get_raw_info(self, file_path: str) -> Dict[str, Any]:
        """Extracts camera metadata from a RAW file."""
        try:
            with rawpy.imread(file_path) as raw:
                # rawpy doesn't expose all EXIF easily but we can get some basics
                info = {
                    "Camera": f"{raw.camera_make.decode()} {raw.camera_model.decode()}",
                    "Width": raw.sizes.width,
                    "Height": raw.sizes.height,
                    "Colors": raw.num_colors,
                    "Bayer Pattern": raw.color_desc.decode(),
                    "ISO": "N/A", # Harder to get from rawpy directly without exif tool
                    "Timestamp": "N/A"
                }
                return info
        except Exception as e:
            print(f"Error reading RAW info {file_path}: {e}")
            return {}

    def read_raw_linear(self, file_path: str, debayer_algo: str = "AHD"):
        """
        Reads a proprietary RAW file and extracts debayered linear RGB data.
        Algorithms: 'AHD', 'Bilinear', 'VNG', 'PPG', 'AAHD'
        """
        print(f"Extracting linear RAW data: {file_path} using {debayer_algo}")
        
        # Map algorithm names to rawpy UserFlip / Demosaic methods
        user_demosaic = 3 # Default AHD
        if debayer_algo == "Bilinear": user_demosaic = 0
        elif debayer_algo == "VNG": user_demosaic = 1
        elif debayer_algo == "PPG": user_demosaic = 2
        elif debayer_algo == "AHD": user_demosaic = 3
        # rawpy doesn't expose AAHD directly as an int usually, but let's stick to these common ones
        
        try:
            with rawpy.imread(file_path) as raw:
                rgb_linear = raw.postprocess(
                    gamma=(1, 1),
                    no_auto_bright=True,
                    output_bps=16,
                    use_camera_wb=True,
                    user_demosaic=user_demosaic
                )
            
            # Convert to 32-bit float and normalize
            rgb_float32 = rgb_linear.astype(np.float32) / 65535.0
            
            # Transpose to (Channels, Height, Width)
            return np.transpose(rgb_float32, (2, 0, 1))
        except Exception as e:
            print(f"Error processing RAW {file_path}: {e}")
            return None

    def save_to_fits(self, data, filename, image_type="LIGHT", extra_headers: Dict[str, Any] = None):
        """
        Saves a numpy array to a standardized FITS file with a basic header.
        """
        output_path = os.path.join(self.output_dir, filename)
        
        # Create a basic header
        header = fits.Header()
        header['PROGRAM'] = 'Astro Preprocessing Toolkit'
        header['IMAGETYP'] = image_type
        header['BZERO'] = 0.0
        header['BSCALE'] = 1.0
        
        if extra_headers:
            for k, v in extra_headers.items():
                header[k] = v
        
        # Create Primary Header Data Unit
        hdu = fits.PrimaryHDU(data=data, header=header)
        hdul = fits.HDUList([hdu])
        
        try:
            hdul.writeto(output_path, overwrite=True)
            print(f"Saved to: {output_path}")
            return output_path
        except Exception as e:
            print(f"Error saving to FITS {output_path}: {e}")
            return None

    def convert_raw_to_fits(self, raw_path, image_type="LIGHT", debayer_algo="AHD"):
        """
        Convenience pipeline method to convert a single RAW to FITS.
        """
        # 1. Extract linear data
        linear_data = self.read_raw_linear(raw_path, debayer_algo)
        if linear_data is None:
            return None
        
        # 2. Format the output filename
        base_name = os.path.basename(raw_path)
        name_without_ext = os.path.splitext(base_name)[0]
        fits_filename = f"{name_without_ext}.fits"
        
        # 3. Save as standardized 32-bit float FITS
        return self.save_to_fits(linear_data, fits_filename, image_type)

    def batch_convert(self, file_paths: List[str], output_dir: str, 
                      image_type: str = "LIGHT", debayer_algo: str = "AHD",
                      progress_callback: Optional[Callable[[int, int, str], None]] = None):
        """Processes a list of files and saves them to the output directory."""
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            
        success_count = 0
        total = len(file_paths)
        
        for i, path in enumerate(file_paths):
            ext = os.path.splitext(path)[1].lower()
            if progress_callback:
                progress_callback(i, total, os.path.basename(path))
                
            if ext in ('.cr2', '.nef', '.arw', '.dng', '.raw'):
                result = self.convert_raw_to_fits(path, image_type, debayer_algo)
                if result: success_count += 1
            elif ext in ('.fits', '.fit', '.fts'):
                # For FITS, we might just standardize them (e.g. convert to float32)
                data, header = self.load_fits(path)
                if data is not None:
                    # Generic standardization
                    data_float = data.astype(np.float32)
                    if data.dtype == np.uint16:
                        data_float /= 65535.0
                    elif data.dtype == np.uint8:
                        data_float /= 255.0
                        
                    filename = os.path.basename(path)
                    result = self.save_to_fits(data_float, filename, image_type, dict(header))
                    if result: success_count += 1
            
        if progress_callback:
            progress_callback(total, total, "Finished")
            
        return success_count