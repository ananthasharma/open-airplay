#!/usr/bin/env python3
"""
AirPlay client implementation in Python.
This module provides functionality to interact with AirPlay devices.
"""

import os
import sys
import time
import argparse
import socket
import http.client
import urllib.parse
import base64
import hashlib
import json
import io
from typing import Dict, List, Optional, Tuple, Union, Any
from PIL import Image, ImageGrab
import zeroconf

class AirPlay:
    """AirPlay client for controlling Apple TV devices."""
    
    # Transition constants
    NONE = 'None'
    SLIDE_LEFT = 'SlideLeft'
    SLIDE_RIGHT = 'SlideRight'
    DISSOLVE = 'Dissolve'
    
    # Default settings
    USERNAME = 'Airplay'
    PORT = 7000
    APPLETV_WIDTH = 1280
    APPLETV_HEIGHT = 720
    APPLETV_ASPECT = APPLETV_WIDTH / APPLETV_HEIGHT
    DNSSD_TYPE = '_airplay._tcp.local.'
    
    def __init__(self, hostname: str, port: int = PORT, name: str = None):
        """
        Initialize AirPlay client.
        
        Args:
            hostname: IP address or hostname of the AirPlay device
            port: Port number (default: 7000)
            name: Friendly name of the device (defaults to hostname if not provided)
        """
        self.hostname = hostname
        self.port = port
        self.name = name if name else hostname
        self.password = None
        self.auth = None
        self.params = None
        self.authorization = None
        self.photo_thread = None
        self.appletv_width = self.APPLETV_WIDTH
        self.appletv_height = self.APPLETV_HEIGHT
        self.appletv_aspect = self.APPLETV_ASPECT
    
    def set_screen_size(self, width: int, height: int) -> None:
        """
        Set the screen size of the AirPlay device.
        
        Args:
            width: Screen width in pixels
            height: Screen height in pixels
        """
        self.appletv_width = width
        self.appletv_height = height
        self.appletv_aspect = width / height
    
    def set_password(self, password: str) -> None:
        """
        Set the password for authentication.
        
        Args:
            password: Password for the AirPlay device
        """
        self.password = password
    
    def set_auth(self, auth: 'Auth') -> None:
        """
        Set the authentication handler.
        
        Args:
            auth: Authentication handler object
        """
        self.auth = auth
    
    def _md5_digest(self, input_str: str) -> str:
        """
        Calculate MD5 digest of a string.
        
        Args:
            input_str: Input string
            
        Returns:
            MD5 digest as a hexadecimal string
        """
        return hashlib.md5(input_str.encode('utf-8')).hexdigest()
    
    def _make_authorization(self, params: Dict[str, str], password: str, method: str, uri: str) -> str:
        """
        Create authorization header for digest authentication.
        
        Args:
            params: Authentication parameters from WWW-Authenticate header
            password: Password for authentication
            method: HTTP method (GET, POST, PUT)
            uri: Request URI
            
        Returns:
            Authorization header value
        """
        realm = params.get('realm')
        nonce = params.get('nonce')
        ha1 = self._md5_digest(f"{self.USERNAME}:{realm}:{password}")
        ha2 = self._md5_digest(f"{method}:{uri}")
        response = self._md5_digest(f"{ha1}:{nonce}:{ha2}")
        
        self.authorization = (
            f'Digest username="{self.USERNAME}", '
            f'realm="{realm}", '
            f'nonce="{nonce}", '
            f'uri="{uri}", '
            f'response="{response}"'
        )
        return self.authorization
    
    def _get_auth_params(self, auth_string: str) -> Dict[str, str]:
        """
        Parse WWW-Authenticate header to extract authentication parameters.
        
        Args:
            auth_string: WWW-Authenticate header value
            
        Returns:
            Dictionary of authentication parameters
        """
        params = {}
        first_space = auth_string.find(' ')
        digest = auth_string[:first_space]
        rest = auth_string[first_space+1:].replace('\r\n', ' ')
        
        for item in rest.split(', '):
            if '=' in item:
                key, value = item.split('=', 1)
                value = value.strip('"')
                params[key] = value
        
        return params
    
    def _set_password(self) -> Optional[str]:
        """
        Get password for authentication, either from stored value or auth handler.
        
        Returns:
            Password string or None if not available
            
        Raises:
            IOError: If authentication is required but no password is available
        """
        if self.password is not None:
            return self.password
        elif self.auth is not None:
            self.password = self.auth.get_password(self.hostname, self.name)
            return self.password
        else:
            raise IOError("Authentication required")
    
    def _do_http(self, method: str, uri: str, data: Optional[bytes] = None, 
                headers: Optional[Dict[str, str]] = None, repeat: bool = True) -> str:
        """
        Perform HTTP request to AirPlay device.
        
        Args:
            method: HTTP method (GET, POST, PUT)
            uri: Request URI
            data: Request body data
            headers: Additional HTTP headers
            repeat: Whether to retry with authentication if needed
            
        Returns:
            Response body as string
            
        Raises:
            IOError: If authentication fails
        """
        if headers is None:
            headers = {}
        
        conn = http.client.HTTPConnection(self.hostname, self.port)
        
        if self.params is not None:
            # Try to reuse password if already set
            headers['Authorization'] = self._make_authorization(self.params, self.password, method, uri)
        
        if headers:
            headers.setdefault('User-Agent', 'MediaControl/1.0')
        
        if data is not None:
            headers['Content-Length'] = str(len(data))
        
        conn.request(method, uri, body=data, headers=headers)
        response = conn.getresponse()
        
        if response.status == 401:
            if repeat:
                auth_header = response.getheader('WWW-Authenticate')
                if self._set_password() is not None:
                    self.params = self._get_auth_params(auth_header)
                    return self._do_http(method, uri, data, headers, False)
                else:
                    return None
            else:
                raise IOError("Incorrect password")
        else:
            response_data = response.read().decode('utf-8')
            conn.close()
            return response_data
    
    def stop(self) -> None:
        """Stop any active AirPlay session."""
        try:
            self.stop_photo_thread()
            self._do_http('POST', '/stop')
            self.params = None
        except Exception:
            pass
    
    def _scale_image(self, image: Image.Image) -> Image.Image:
        """
        Scale image to fit AirPlay device screen size.
        
        Args:
            image: PIL Image object
            
        Returns:
            Scaled PIL Image object
        """
        width, height = image.size
        
        if width <= self.appletv_width and height <= self.appletv_height:
            return image
        
        image_aspect = width / height
        
        if image_aspect > self.appletv_aspect:
            scaled_width = self.appletv_width
            scaled_height = int(self.appletv_width / image_aspect)
        else:
            scaled_height = self.appletv_height
            scaled_width = int(self.appletv_height * image_aspect)
        
        return image.resize((scaled_width, scaled_height), Image.LANCZOS)
    
    def photo(self, image_source: Union[str, Image.Image], transition: str = NONE) -> None:
        """
        Display a photo on the AirPlay device.
        
        Args:
            image_source: Path to image file or PIL Image object
            transition: Transition effect (NONE, SLIDE_LEFT, SLIDE_RIGHT, DISSOLVE)
        """
        self.stop_photo_thread()
        
        if isinstance(image_source, str):
            image = Image.open(image_source)
        else:
            image = image_source
        
        scaled_image = self._scale_image(image)
        self._photo_raw(scaled_image, transition)
        
        # Start a thread to keep the photo displayed
        import threading
        self.photo_thread = threading.Thread(
            target=self._photo_keep_alive, 
            args=(scaled_image,)
        )
        self.photo_thread.daemon = True
        self.photo_thread.start()
    
    def _photo_keep_alive(self, image: Image.Image, interval: int = 5) -> None:
        """
        Thread function to keep a photo displayed by periodically refreshing it.
        
        Args:
            image: PIL Image object
            interval: Refresh interval in seconds
        """
        while True:
            try:
                self._photo_raw(image, self.NONE)
                time.sleep(interval)
            except Exception:
                break
    
    def _photo_raw(self, image: Image.Image, transition: str) -> None:
        """
        Send a photo to the AirPlay device.
        
        Args:
            image: PIL Image object
            transition: Transition effect
        """
        headers = {'X-Apple-Transition': transition}
        
        # Convert image to JPEG
        img_buffer = io.BytesIO()
        image.save(img_buffer, format='JPEG')
        img_data = img_buffer.getvalue()
        
        self._do_http('PUT', '/photo', img_data, headers)
    
    def stop_photo_thread(self) -> None:
        """Stop the photo keep-alive thread if running."""
        if self.photo_thread and self.photo_thread.is_alive():
            self.photo_thread = None
    
    def desktop(self) -> None:
        """
        Stream desktop to the AirPlay device.
        
        Note: This requires PIL's ImageGrab which works on Windows and macOS.
        """
        self.stop_photo_thread()
        
        import threading
        self.photo_thread = threading.Thread(target=self._desktop_thread)
        self.photo_thread.daemon = True
        self.photo_thread.start()
    
    def _desktop_thread(self, interval: float = 0.5) -> None:
        """
        Thread function to capture and stream desktop.
        
        Args:
            interval: Capture interval in seconds
        """
        while True:
            try:
                screen = ImageGrab.grab()
                scaled_screen = self._scale_image(screen)
                self._photo_raw(scaled_screen, self.NONE)
                time.sleep(interval)
            except Exception as e:
                print(f"Desktop streaming error: {e}")
                break

    @staticmethod
    def capture_screen() -> Image.Image:
        """
        Capture the screen.
        
        Returns:
            PIL Image of the screen
        """
        return ImageGrab.grab()

    @staticmethod
    def search(timeout: int = 1000) -> List['Service']:
        """
        Search for AirPlay devices on the network.
        
        Args:
            timeout: Search timeout in milliseconds
            
        Returns:
            List of Service objects representing found AirPlay devices
        """
        services = []
        
        # Use zeroconf for service discovery
        zc = zeroconf.Zeroconf()
        browser = ServiceBrowser(zc, AirPlay.DNSSD_TYPE)
        
        # Wait for the specified timeout
        time.sleep(timeout / 1000)
        
        # Get discovered services
        for service in browser.get_services():
            services.append(service)
        
        zc.close()
        return services


class Auth:
    """Base authentication handler interface."""
    
    def get_password(self, hostname: str, name: str) -> Optional[str]:
        """
        Get password for an AirPlay device.
        
        Args:
            hostname: Device hostname or IP
            name: Device friendly name
            
        Returns:
            Password string or None if not available
        """
        raise NotImplementedError("Subclasses must implement get_password")


class AuthConsole(Auth):
    """Console-based authentication handler."""
    
    def get_password(self, hostname: str, name: str) -> Optional[str]:
        """
        Prompt user for password in console.
        
        Args:
            hostname: Device hostname or IP
            name: Device friendly name
            
        Returns:
            Password string entered by user
        """
        display = hostname if hostname == name else f"{name} ({hostname})"
        return input(f"Please input password for {display}: ")


class Service:
    """Represents an AirPlay service discovered on the network."""
    
    def __init__(self, hostname: str, port: int = AirPlay.PORT, name: str = None):
        """
        Initialize Service object.
        
        Args:
            hostname: Device hostname or IP
            port: Device port
            name: Device friendly name
        """
        self.hostname = hostname
        self.port = port
        self.name = name if name else hostname


class ServiceBrowser:
    """Browser for AirPlay services using zeroconf."""
    
    def __init__(self, zc: zeroconf.Zeroconf, service_type: str):
        """
        Initialize service browser.
        
        Args:
            zc: Zeroconf instance
            service_type: Service type to browse for
        """
        self.zc = zc
        self.service_type = service_type
        self.services = []
        
        # Set up listener
        self.listener = ServiceListener(self)
        self.browser = zeroconf.ServiceBrowser(zc, service_type, self.listener)
    
    def add_service(self, zc: zeroconf.Zeroconf, service_type: str, name: str) -> None:
        """
        Add discovered service.
        
        Args:
            zc: Zeroconf instance
            service_type: Service type
            name: Service name
        """
        info = zc.get_service_info(service_type, name)
        if info:
            # Get IP address
            addresses = [socket.inet_ntoa(addr) for addr in info.addresses]
            if addresses:
                service = Service(addresses[0], info.port, info.name)
                self.services.append(service)
    
    def get_services(self) -> List[Service]:
        """
        Get discovered services.
        
        Returns:
            List of Service objects
        """
        return self.services


class ServiceListener:
    """Listener for zeroconf service events."""
    
    def __init__(self, browser: ServiceBrowser):
        """
        Initialize service listener.
        
        Args:
            browser: ServiceBrowser instance
        """
        self.browser = browser
    
    def add_service(self, zc: zeroconf.Zeroconf, service_type: str, name: str) -> None:
        """
        Handle service added event.
        
        Args:
            zc: Zeroconf instance
            service_type: Service type
            name: Service name
        """
        self.browser.add_service(zc, service_type, name)
    
    def remove_service(self, zc: zeroconf.Zeroconf, service_type: str, name: str) -> None:
        """
        Handle service removed event.
        
        Args:
            zc: Zeroconf instance
            service_type: Service type
            name: Service name
        """
        pass
    
    def update_service(self, zc: zeroconf.Zeroconf, service_type: str, name: str) -> None:
        """
        Handle service updated event.
        
        Args:
            zc: Zeroconf instance
            service_type: Service type
            name: Service name
        """
        pass


def main() -> None:
    """Command-line interface for AirPlay client."""
    parser = argparse.ArgumentParser(description='AirPlay client')
    parser.add_argument('-h', '--host', required=True, help='Hostname or IP of AirPlay device (with optional port, e.g., 192.168.1.10:7000)')
    parser.add_argument('-s', '--stop', action='store_true', help='Stop current AirPlay session')
    parser.add_argument('-p', '--photo', help='Display photo from file')
    parser.add_argument('-d', '--desktop', action='store_true', help='Stream desktop to AirPlay device')
    parser.add_argument('-t', '--transition', choices=[AirPlay.NONE, AirPlay.SLIDE_LEFT, AirPlay.SLIDE_RIGHT, AirPlay.DISSOLVE],
                        default=AirPlay.NONE, help='Transition effect for photos')
    
    args = parser.parse_args()
    
    # Parse host and port
    if ':' in args.host:
        hostname, port = args.host.split(':')
        airplay = AirPlay(hostname, int(port))
    else:
        airplay = AirPlay(args.host)
    
    # Set authentication handler
    airplay.set_auth(AuthConsole())
    
    if args.stop:
        airplay.stop()
    elif args.photo:
        airplay.photo(args.photo, args.transition)
        input('Press Enter to quit...')
    elif args.desktop:
        try:
            airplay.desktop()
            print('Streaming desktop. Press Ctrl+C to quit...')
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            airplay.stop()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()