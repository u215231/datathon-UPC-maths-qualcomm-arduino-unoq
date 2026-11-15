#!/usr/bin/env bash
# On the laptop, board on USB: keep the board's ports reachable, also after the board is unplugged and plugged back.
#   bash owl/usb.sh        (leave it running; Ctrl+C to stop)
# 8000 = Uino's page on the board, 7000 = the LED eyes, 28081/28082/28084 = the models, for a page served by the laptop.
while true; do
  if [ "$(adb forward --list 2>/dev/null | wc -l)" -lt 5 ]; then
    adb forward tcp:8000 tcp:8000 >/dev/null 2>&1
    adb forward tcp:7000 tcp:7000 >/dev/null 2>&1
    adb forward tcp:28081 tcp:8081 >/dev/null 2>&1
    adb forward tcp:28082 tcp:8082 >/dev/null 2>&1
    adb forward tcp:28084 tcp:8084 >/dev/null 2>&1
  fi
  sleep 2
done
