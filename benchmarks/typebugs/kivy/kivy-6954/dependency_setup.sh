sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    libportmidi-dev \
    libswscale-dev \
    libavformat-dev \
    libavcodec-dev \
    libjpeg-dev \
    zlib1g-dev

pip install -r ./pyter_requirements.txt
python -m pip install -e ".[dev,full]"

