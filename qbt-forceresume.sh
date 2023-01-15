#!/bin/bash
#######################################################################################
#
#       qBt-mover scripts by Jarsky
#
#       v1.0  15/01/2023
#
#       qbt-forceresume.sh
#       This script was written to connect to UnRAID and check if the mover has
#       finished. If not, it will try again up to the defined times. If it still
#       hasnt finished it will force-resume anyway and end the script. 
#
#       Usage
#       
#       You need to setup an SSH key to automate and test its working
#       
#       ./qbit-forceresume.sh           will run straight away without checking mover
#       ./qbit-forceresume.sh -mover    will run the mover check
#
#
#######################################################################################

#Variables
countMax=6
sleepDuration=600
logLineTail=20
logFile=/var/log/qbt-mover.log
remote_host="root@jarskynas"


#Script :: shouldnt need to edit below this line

dateFormat() {
    date +"[%Y-%m-%d %H:%M:%S]"
}

if [ ! -w $logFile ]; then
    echo "$(dateFormat) [ERROR] $logFile is not writable by this script."
    echo "$(dateFormat) [ERROR] You need to change log path, run as SUDO or set permission. e.g sudo touch $logFile && sudo chmod 755 $logFile"
    exit 1
fi

# Check if the -mover argument is passed
if [[ $1 == "-mover" ]]; then
    while true; do
        qbtfrCount=0
        # Get the last 10 lines of the log from remote host
        log=$(ssh $remote_host "cat /var/log/syslog" | tail -n $logLineTail)

        # Check if the log contains the desired line
        if echo "$log" | grep -q "exit.*/usr/local/sbin/mover"; then
            echo "$(dateFormat) [INFO] Mover has stopped running." >> $logFile
            echo "$(dateFormat) [INFO] Force resuming ALL torrents" >> $logFile
            qbt torrent force-resume ALL
            break
        fi

        # Increase the count
        qbtfrCount=$((qbtfrCount + 1))

        # Check if the count has reached countMax
        if [ $qbtfrCount -eq $countMax ]; then
            echo "$(dateFormat) [WARN] Mover is still running." >> $logFile
            echo "$(dateFormat) [INFO] Force resuming ALL torrents." >> $logFile
            qbt torrent force-resume ALL
            break
        fi

        # Wait for sleepDuration seconds
        sleep $sleepDuration
    done
else
    echo "$(dateFormat) [INFO] Force resuming ALL torrents." >> $logFile
    qbt torrent force-resume ALL
fi
