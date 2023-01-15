#!/bin/bash
#######################################################################################
#
#       qBt-mover scripts by Jarsky
#       v1.0  15/01/2023
#
#       qbt-pause.sh
#       This script will find torrents currently stalled or seeding and pause them to
#       release file locks so they can be moved off the cache
#
#######################################################################################

#Variables
jsonFilename=qbt.json
logFile=/var/log/qbt-mover.log
states=("stalledUP" "uploading" "errored")

#Script :: shouldnt need to edit below this line

dateFormat() {
    date +"[%Y-%m-%d %H:%M:%S]"
}

if [ ! -w $logFile ]; then
    echo "$(dateFormat) [ERROR] $logFile is not writable by this script."
    echo "$(dateFormat) [ERROR] You need to change log path, run as SUDO or set permission. e.g sudo touch $logFile && sudo chmod 755 $logFile"
    exit 1
fi

# export torrent list as json
qbt torrent list -F json > $jsonFilename
echo "$(dateFormat) [INFO] JSON file exported successfully" >> $logFile

#parse json file and find all torrents with "state"
hashes=""
for state in "${states[@]}"; do
    hashes="$hashes $(jq -r '.[] | select(.state=="'$state'") | .hash' $jsonFilename)"
done

# loop through each hash and pause the corresponding torrent
for hash in $hashes; do
    name=$(jq -r '.[] | select(.hash=="'$hash'") | .name' $jsonFilename)
    qbt torrent pause $hash
    echo "$(dateFormat) [INFO] Torrent Paused: $name :: Hash: ${hash:0:5}" >> $logFile
done

rm -f $jsonFilename