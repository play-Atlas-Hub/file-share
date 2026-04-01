#!/bin/bash

python3 server/server_complete.py &
python3 server/website.py &
python3 client/client_complete.py