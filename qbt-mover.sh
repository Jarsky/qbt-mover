#!/bin/bash
####################################################################################################
#
#       qbt-mover scripts by Jarsky
#
#       Updated:  15/01/2023
        version="v1.2"
        Name="qbt-mover"
#       Summary:
#
#       This script is intended for UnRAID and its Cache.
#       It will find torrents currently stalled or seeding and pause them to release file locks
#       so they can be moved off the cache. It can also check if the mover has finished and
#       force-resume all torrents if necessary.
#
#       Pre-requisites:
#       Install qbittorrent-cli:  https://github.com/fedarovich/qbittorrent-cli
#       You need to setup an SSH key: https://phoenixnap.com/kb/setup-passwordless-ssh
#
#       Usage:
#
#       ./qbt-mover.sh                      Shows available switches
#       ./qbt-mover.sh -pause               Will pause all active torrents
#       ./qbt-mover.sh -force-resume        Will force-resume all torrents
#       ./qbt-mover.sh -force-resume mover  Will check mover has finished before resuming
#
#       Mover Check:
#       Will check the UnRAID log. If the mover hasn't exited, it will sleep and try again
#       until the script reaches max count, after whichh it will just force-resume anyway.
#       This is to minimise the time the torrents are stopped from seeding
#
#####################################################################################################

#Variables
countMax=6
sleepDuration=600
logLineTail=20
logFile=/var/log/qbt-mover.log
remote_host="root@tower"
states=("stalledUP" "uploading" "errored")
jsonFilename=qbt.json
qbtcliSettings=~/.qbt/settings.json

#Script

dateFormat() {
    date +"[%Y-%m-%d %H:%M:%S]"
}

# Color codes
if [[ -t 1 ]]; then
   red=$(tput setaf 1)
   yellow=$(tput setaf 3)
   white=$(tput setaf 7)
   teal=$(tput setaf 6)
   magenta=$(tput setaf 5)
   reset=$(tput sgr0)
fi

# Logging levels
ERROR="${red}[ERROR]${reset}"
WARN="${yellow}[WARN]${reset}"
INFO="${teal}[INFO]${reset}"


function logCheck() {
    if [ ! -w $logFile ]; then
        echo -e "$(dateFormat) ${ERROR} $logFile is not writable by this script."
        echo -e "$(dateFormat) ${ERROR} You need to change log path, run as SUDO or set permission."
        echo -e "$(dateFormat) ${WARN} You could try sudo touch $logFile && sudo chmod 755 $logFile"
        exit 1
    fi
    }

function qbtcliCheck() {
    if [ ! -f $qbtcliSettings ]; then
        echo -e "$(dateFormat) ${WARN} The qBitTorrent CLI settings file hasn't been configured."
        echo -e "$(dateFormat) ${WARN} Make sure to run 'qbt settings' to check configuration."
    fi
}

function checkSettings() {
    logCheck
    qbtcliCheck
}

if [[ $# -eq 0 ]]; then
  echo -e "$(dateFormat) ${WARN} No switches were defined."
  echo -e "$(dateFormat) ${INFO} You need to enter a switch. for a list use $0 --help"
  exit 1
fi

if [[ $1 == "-h" || $1 == "--help" ]]; then
    echo -e "${teal}$Name${reset} | ${yellow}Version:${reset} $version | ${red}Repo:${reset} https://github.com/jarsky/qbt-mover

    Help [ -h | --help ]
    Version [ -v | --version ]

    Usage $0 [-command] [arg]
 	
    Commands:

    -pause                      Will pause all active torrents
    -force-resume               Will force-resume all torrents
    -force-resume mover         Will check mover has finished before resuming
    -cron                       Will show CRON options"
    echo -e ""

elif [[ $1 == "-v" || $1 == "--version" ]]; then
    echo -e ""
    echo -e "${teal}$Name${reset} | ${yellow}Version:${reset} $version | ${red}Repo:${reset} https://github.com/jarsky/qbt-mover
    
    ${magenta}Author${reset}: Jarsky
    ${magenta}Update 1.2${reset}: Concatinated scripts and added CRON
    ${magenta}Update 1.0${reset}: Scripts working, reached released"
    echo -e ""

elif [[ $1 == "-force-resume" ]]; then
    checkSettings
    if [[ $2 == "mover" ]]; then
        checkSettings
        while true; do
                qbtfrCount=0
		echo -e "Checking UnRAID Log"
                # Get the last 10 lines of the log from remote host
                log=$(ssh $remote_host "cat /var/log/syslog" | tail -n $logLineTail)

                # Check if the log contains the desired line
                if echo "$log" | grep -q "exit.*/usr/local/sbin/mover"; then
                    echo -e "$(dateFormat) ${INFO} Mover has stopped running." >> $logFile
                    echo -e "$(dateFormat) ${INFO} Force resuming ALL torrents" >> $logFile
                    qbt torrent force-resume ALL
                    break
                fi

                # Increase the count
                qbtfrCount=$((qbtfrCount + 1))

                # Check if the count has reached countMax
                if [ $qbtfrCount -eq $countMax ]; then
                    echo -e "$(dateFormat) ${WARN} Mover is still running. Stopping Mover." >> $logFile
                    echo -e "$(dateFormat) ${INFO} Force resuming ALL torrents." >> $logFile
                    ssh $remote_host "mover stop"
                    sleep 5
                    qbt torrent force-resume ALL
                    break
                fi
                # Calculations for the log
                countRemaining=$(expr $countMax - $qbtfrCount)
                ((min=$sleepDuration/60))
                ((totaltime=$countRemaining*$min))
                    echo -e "$(dateFormat) ${WARN} Mover is still running." >> $logFile
                    echo -e "$(dateFormat) ${INFO} Sleeping for $min minutes." >> $logFile
                    echo -e "$(dateFormat) ${INFO} Will retry $countRemaining more times (ETA: $totaltime minutes)." >> $logFile
                # Wait for sleepDuration seconds
                sleep $sleepDuration
            done
    else
            echo -e "$(dateFormat) ${INFO} Force resuming ALL torrents." >> $logFile
            qbt torrent force-resume ALL
    fi

elif [[ $1 == "-pause" ]]; then
        checkSettings
        # export torrent list as json
        qbt torrent list -F json > $jsonFilename
        echo -e "$(dateFormat) ${INFO} JSON file exported successfully" >> $logFile

        #parse json file and find all torrents with "state"
        hashes=""
        for state in "${states[@]}"; do
            hashes="$hashes $(jq -r '.[] | select(.state=="'$state'") | .hash' $jsonFilename)"
        done

        # loop through each hash and pause the corresponding torrent
        for hash in $hashes; do
            name=$(jq -r '.[] | select(.hash=="'$hash'") | .name' $jsonFilename)
            qbt torrent pause $hash
            echo -e "$(dateFormat) ${INFO} Torrent Paused: Hash ${teal}${hash:0:5}${reset} :: Name $name" >> $logFile
        done

        rm -f $jsonFilename

elif [[ $1 == "-cron" ]]; then
        current_dir=$(pwd)
        cronuser=${teal}$(whoami)${reset}
    if [[ $# -eq 1 ]]; then
        echo -e "${teal}$Name${reset} | ${yellow}Version:${reset} $version | ${red}Repo:${reset} https://github.com/jarsky/qbt-mover

        Usage $0 -cron [command] [arg]

        all                    Will add all cron entries
        pause                  Will add cron entry for pausing
        force-resume           Will add cron entry for force-resuming
        force-resume mover     Will add cron entry for force-resuming mover
        remove                 Will delete all cron entries"
        echo -e ""
    fi
    if [[ $2 == "all" ]]; then
        checkSettings
        if [[ -z `crontab -l | grep "## qbt-mover"` ]]; then
            (crontab -l 2>/dev/null; echo "## qbt-mover cron") | crontab -
        fi
        if [[ -z `crontab -l | grep "qbt-mover.*pause"` ]]; then
            (crontab -l 2>/dev/null; echo "35 3 * * *      cd $current_dir && ./qbt-mover.sh -pause") | crontab -
            echo -e "$(dateFormat) ${INFO} CRON Job [pause] created for $cronuser" >> $logFile
        else echo -e "$(dateFormat) ${INFO} CRON Job [pause] already exists for $cronuser" >> $logFile
        fi
        if [[ -z `crontab -l | grep "qbt-mover.*force-resume mover"` ]]; then
            (crontab -l 2>/dev/null; echo "45 3 * * *      cd $current_dir && ./qbt-mover.sh -force-resume mover") | crontab -
            echo -e "$(dateFormat) ${INFO} CRON Job [force-resume mover] created for $cronuser" >> $logFile
        else echo -e "$(dateFormat) ${INFO} CRON Job [force-resume mover] already exists for $cronuser" >> $logFile
        fi
    elif [[ $2 == "pause" ]]; then
        checkSettings
        if [[ -z `crontab -l | grep "## qbt-mover"` ]]; then
            (crontab -l 2>/dev/null; echo "## qbt-mover cron") | crontab -
        fi
        if [[ -z `crontab -l | grep "qbt-mover.*pause"` ]]; then
            (crontab -l 2>/dev/null; echo "35 3 * * *      cd $current_dir && ./qbt-mover.sh -pause") | crontab -
            echo -e "$(dateFormat) ${INFO} CRON Job [pause] created for $cronuser" >> $logFile
        else echo -e "$(dateFormat) ${INFO} CRON Job [pause] already exists for $cronuser" >> $logFile
        fi

    elif [[ $2 == "force-resume" ]]; then
        checkSettings
        if [[ $3 == "mover" ]]; then
            if [[ -z `crontab -l | grep "## qbt-mover"` ]]; then
                (crontab -l 2>/dev/null; echo "## qbt-mover cron") | crontab -
            fi
            if [[ -z `crontab -l | grep "qbt-mover.*force-resume mover"` ]]; then
                (crontab -l 2>/dev/null; echo "45 3 * * *      cd $current_dir && ./qbt-mover.sh -force-resume mover") | crontab -
                echo -e "$(dateFormat) ${INFO} CRON Job [force-resume mover] created for $cronuser" >> $logFile
            else echo -e "$(dateFormat) ${INFO} CRON Job [force-resume mover] already exists for $cronuser" >> $logFile
            fi
        else
            if [[ -z `crontab -l | grep "## qbt-mover"` ]]; then
                (crontab -l 2>/dev/null; echo "## qbt-mover cron") | crontab -
            fi
            if [[ -z `crontab -l | grep "qbt-mover.*force-resume$"` ]]; then
                (crontab -l 2>/dev/null; echo "0 4 * * *      cd $current_dir && ./qbt-mover.sh -force-resume") | crontab -
                echo -e "$(dateFormat) ${INFO} CRON Job [force-resume] created for $cronuser" >> $logFile
            else echo -e "$(dateFormat) ${INFO} CRON Job [force-resume] already exists for $cronuser" >> $logFile
            fi
        fi
    elif [[ $2 == "remove" ]]; then
        checkSettings
            cronjobs=$(crontab -l | grep "qbt-mover")
            if [[ -z $cronjobs ]]; then
                echo -e "$(dateFormat) ${ERROR} CRON No qbt-mover jobs found for $cronuser" >> $logFile
            else
                crontab -l | grep -v "qbt-mover" | crontab -
                echo -e "$(dateFormat) ${INFO} CRON All qbt-mover jobs have been removed from $cronuser" >> $logFile
            fi
        fi
fi