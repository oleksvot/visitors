#!/bin/bash

APPNAME=visitors

# Use script's directory as current
cd "$(dirname "$(realpath "$0")")";
if [ $(id -u) = 0 ] ; then echo "Please don't run as root" ; exit 1 ; fi

# Create python's virtual env if it hasn't already been done, and activate it
[ ! -d env ] && python3 -m venv env
source env/bin/activate

# Install/Upgrade packages inside virtual env
pip3 install sanic sanic-ext aiogram python-geoip-python3 python-geoip-geolite2 pycountry aiosmtplib

# Generate systemd unit
cat <<EOF | sudo tee /etc/systemd/system/$APPNAME.service
[Unit]
Description=$APPNAME

[Service]
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/env/bin/python3 visitors.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Activate it
sudo systemctl daemon-reload
sudo systemctl enable $APPNAME
# Use this command to restart backend
sudo systemctl restart $APPNAME