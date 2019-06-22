#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
cd $DIR

while true; do
  python photobooth.py >> photobooth.log 2>&1
  sleep 5
done

