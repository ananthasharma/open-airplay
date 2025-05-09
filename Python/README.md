# Python AirPlay Client

This is a Python implementation of an AirPlay client that allows you to interact with AirPlay devices (like Apple TV) from Python applications.

## Features

- Display photos on AirPlay devices
- Stream desktop to AirPlay devices
- Discover AirPlay devices on the local network
- Support for authentication
- Support for different transition effects

## Requirements

- Python 3.10+
- Pillow (for image processing)
- zeroconf (for service discovery)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### As a Command-Line Tool

```bash
# Display a photo
python airplay.py --host 192.168.1.10 --photo /path/to/image.jpg

# Display a photo with transition effect
python airplay.py --host 192.168.1.10 --photo /path/to/image.jpg --transition SlideLeft

# Stream desktop
python airplay.py --host 192.168.1.10 --desktop

# Stop current session
python airplay.py --host 192.168.1.10 --stop
```

### As a Library

```python
from airplay import AirPlay
from PIL import Image

# Create AirPlay client
airplay = AirPlay("192.168.1.10")

# Display a photo
airplay.photo("/path/to/image.jpg")

# Display a photo with transition
airplay.photo("/path/to/image.jpg", AirPlay.SLIDE_LEFT)

# Display a PIL Image
image = Image.open("/path/to/image.jpg")
airplay.photo(image)

# Stream desktop
airplay.desktop()

# Stop current session
airplay.stop()

# Discover AirPlay devices
services = AirPlay.search()
for service in services:
    print(f"Found: {service.name} at {service.hostname}:{service.port}")
```

## Authentication

If the AirPlay device requires authentication, you can provide a password:

```python
airplay = AirPlay("192.168.1.10")
airplay.set_password("your_password")
```

Or use the built-in console authentication handler:

```python
from airplay import AirPlay, AuthConsole

airplay = AirPlay("192.168.1.10")
airplay.set_auth(AuthConsole())
```

## Custom Screen Size

If your AirPlay device has a different resolution than the default 1280x720:

```python
airplay = AirPlay("192.168.1.10")
airplay.set_screen_size(1920, 1080)  # For 1080p
```