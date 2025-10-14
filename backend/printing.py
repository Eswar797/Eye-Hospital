try:
    from escpos.printer import Network
    from escpos.printer import Usb
    ESCPOS_AVAILABLE = True
except ImportError:
    ESCPOS_AVAILABLE = False
    Network = None
    Usb = None

from PIL import Image, ImageDraw, ImageFont
import io
import os
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class PrinterManager:
    def __init__(self):
        self.printer_ip = os.getenv("PRINTER_IP", "192.168.1.100")
        self.printer_port = int(os.getenv("PRINTER_PORT", "9100"))
        self.printer = None
        self._initialize_printer()

    def _initialize_printer(self):
        """Initialize the printer connection"""
        if not ESCPOS_AVAILABLE:
            logger.warning("escpos library not available - printer functionality disabled")
            self.printer = None
            return
            
        try:
            # Try network printer first
            self.printer = Network(self.printer_ip, port=self.printer_port)
            logger.info(f"Connected to network printer at {self.printer_ip}:{self.printer_port}")
        except Exception as e:
            logger.warning(f"Failed to connect to network printer: {e}")
            try:
                # Fallback to USB printer
                self.printer = Usb()
                logger.info("Connected to USB printer")
            except Exception as e2:
                logger.error(f"Failed to connect to USB printer: {e2}")
                self.printer = None

    def print_token(self, token_number: str, patient_name: str, opd_number: Optional[str] = None) -> bool:
        """Print a patient token"""
        if not self.printer:
            logger.error("No printer available")
            return False

        try:
            # Create token image
            img = self._create_token_image(token_number, patient_name, opd_number)
            
            # Print the image
            self.printer.image(img)
            self.printer.cut()
            
            logger.info(f"Printed token for {token_number}")
            return True
        except Exception as e:
            logger.error(f"Failed to print token: {e}")
            return False

    def print_opd_slip(self, token_number: str, patient_name: str, opd_number: str, 
                      registration_time: str, estimated_wait: Optional[int] = None) -> bool:
        """Print an OPD slip"""
        if not self.printer:
            logger.error("No printer available")
            return False

        try:
            # Create OPD slip image
            img = self._create_opd_slip_image(
                token_number, patient_name, opd_number, 
                registration_time, estimated_wait
            )
            
            # Print the image
            self.printer.image(img)
            self.printer.cut()
            
            logger.info(f"Printed OPD slip for {token_number}")
            return True
        except Exception as e:
            logger.error(f"Failed to print OPD slip: {e}")
            return False

    def _create_token_image(self, token_number: str, patient_name: str, opd_number: Optional[str] = None) -> Image.Image:
        """Create a token image"""
        # Image dimensions (80mm thermal printer)
        width, height = 576, 400  # 80mm = 576 pixels at 203 DPI
        
        # Create image with white background
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        
        # Try to load a font, fallback to default
        try:
            title_font = ImageFont.truetype("arial.ttf", 24)
            normal_font = ImageFont.truetype("arial.ttf", 16)
            small_font = ImageFont.truetype("arial.ttf", 12)
        except:
            title_font = ImageFont.load_default()
            normal_font = ImageFont.load_default()
            small_font = ImageFont.load_default()
        
        # Draw header
        draw.text((width//2, 20), "EYE HOSPITAL", fill='black', font=title_font, anchor="mm")
        draw.text((width//2, 50), "PATIENT TOKEN", fill='black', font=normal_font, anchor="mm")
        
        # Draw line
        draw.line([(50, 70), (width-50, 70)], fill='black', width=2)
        
        # Draw token number (large)
        draw.text((width//2, 120), f"TOKEN: {token_number}", fill='black', font=title_font, anchor="mm")
        
        # Draw patient name
        draw.text((width//2, 160), f"Patient: {patient_name}", fill='black', font=normal_font, anchor="mm")
        
        # Draw OPD number if provided
        if opd_number:
            draw.text((width//2, 190), f"OPD: {opd_number.upper()}", fill='black', font=normal_font, anchor="mm")
        
        # Draw timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        draw.text((width//2, 250), f"Time: {timestamp}", fill='black', font=small_font, anchor="mm")
        
        # Draw footer
        draw.text((width//2, 320), "Please wait for your turn", fill='black', font=small_font, anchor="mm")
        draw.text((width//2, 350), "Thank you for your patience", fill='black', font=small_font, anchor="mm")
        
        return img

    def _create_opd_slip_image(self, token_number: str, patient_name: str, opd_number: str,
                              registration_time: str, estimated_wait: Optional[int] = None) -> Image.Image:
        """Create an OPD slip image"""
        # Image dimensions (80mm thermal printer)
        width, height = 576, 600  # 80mm = 576 pixels at 203 DPI
        
        # Create image with white background
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        
        # Try to load a font, fallback to default
        try:
            title_font = ImageFont.truetype("arial.ttf", 24)
            normal_font = ImageFont.truetype("arial.ttf", 16)
            small_font = ImageFont.truetype("arial.ttf", 12)
        except:
            title_font = ImageFont.load_default()
            normal_font = ImageFont.load_default()
            small_font = ImageFont.load_default()
        
        # Draw header
        draw.text((width//2, 20), "EYE HOSPITAL", fill='black', font=title_font, anchor="mm")
        draw.text((width//2, 50), "OPD SLIP", fill='black', font=normal_font, anchor="mm")
        
        # Draw line
        draw.line([(50, 70), (width-50, 70)], fill='black', width=2)
        
        # Draw token number
        draw.text((width//2, 120), f"TOKEN: {token_number}", fill='black', font=title_font, anchor="mm")
        
        # Draw patient details
        draw.text((50, 160), f"Patient Name: {patient_name}", fill='black', font=normal_font)
        draw.text((50, 190), f"OPD Number: {opd_number.upper()}", fill='black', font=normal_font)
        draw.text((50, 220), f"Registration Time: {registration_time}", fill='black', font=normal_font)
        
        # Draw estimated wait time if provided
        if estimated_wait:
            draw.text((50, 250), f"Estimated Wait: {estimated_wait} minutes", fill='black', font=normal_font)
        
        # Draw instructions
        draw.line([(50, 300), (width-50, 300)], fill='black', width=1)
        draw.text((width//2, 330), "INSTRUCTIONS:", fill='black', font=normal_font, anchor="mm")
        draw.text((50, 360), "1. Proceed to the assigned OPD", fill='black', font=small_font)
        draw.text((50, 380), "2. Wait for your turn", fill='black', font=small_font)
        draw.text((50, 400), "3. Keep this slip with you", fill='black', font=small_font)
        draw.text((50, 420), "4. Follow staff instructions", fill='black', font=small_font)
        
        # Draw footer
        draw.text((width//2, 500), "Thank you for choosing our hospital", fill='black', font=small_font, anchor="mm")
        draw.text((width//2, 530), "For queries, contact reception", fill='black', font=small_font, anchor="mm")
        
        return img

    def test_print(self) -> bool:
        """Test printer connection"""
        if not self.printer:
            return False
        
        try:
            self.printer.text("Printer Test\n")
            self.printer.text("Eye Hospital System\n")
            self.printer.text("Connection successful\n")
            self.printer.cut()
            return True
        except Exception as e:
            logger.error(f"Printer test failed: {e}")
            return False

# Global printer instance
printer_manager = PrinterManager()

