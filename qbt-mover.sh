#!/bin/bash
####################################################################################################
#
#       qbt-mover scripts by Jarsky
#
#       Updated:  19/01/2023
#       Version:  v1.2.2  
#       
#       Summary:
#           This script is intended for qBitTorrent and UnRAID's Mover. 
#           Intended to help with moving files off the cache. 
#
#       Pre-requisites:
#           Install qbittorrent-cli:  https://github.com/fedarovich/qbittorrent-cli
#           Setup an SSH key: https://phoenixnap.com/kb/setup-passwordless-ssh
#           Install jq: apt install -y jq
#
#       Usage:
#           ./qbt-mover.sh --help         Shows all commands
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
qbitCLIsettings=~/.qbt/settings.json


###### You shouldnt need to edit below this line ######
#######################################################

version="v1.2.2"
Name="qbt-mover"

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

### Check Functions

function logCheck() {
    if [ ! -w $logFile ]; then
        echo -e "$(dateFormat) ${ERROR} $logFile is not writable by this script."
        echo -e "$(dateFormat) ${ERROR} You need to change log path, run as SUDO or set permission."
        echo -e "$(dateFormat) ${WARN} You could try sudo touch $logFile && sudo chmod 755 $logFile"
        exit 1
    fi
    }

function qbitCLIcheck() {
    if [ ! -f $qbitCLIsettings ]; then
        echo -e "$(dateFormat) ${WARN} The qBitTorrent CLI settings file hasn't been configured."
        echo -e "$(dateFormat) ${WARN} Make sure to run 'qbt settings' to check configuration."
    fi
    }

function jqCheck() {
    if ! command -v jq > /dev/null 2>&1; then
        echo -e "$(dateFormat) ${ERROR} jq is not installed. Please install jq and run the script again."
        exit 1
    fi
    }

function checkSettings() {
    logCheck
    qbitCLIcheck
    jqCheck
    }

#### General Messages
function helpCMD(){
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
}

function versionCMD(){
        echo -e ""
        echo -e "${teal}$Name${reset} | ${yellow}Version:${reset} $version | ${red}Repo:${reset} https://github.com/jarsky/qbt-mover

        ${magenta}Author${reset}: Jarsky
        ${magenta}Update 1.2.2${reset}: Refactor the code to make it more readable
        ${magenta}Update 1.2.1${reset}: Fix calculations, put more checks
        ${magenta}Update 1.2${reset}: Concatinated scripts and added CRON"
        echo -e ""
}

#### qbt-mover functions

function forceResume() {
  checkSettings
  echo -e "$(dateFormat) ${INFO} Force resuming ALL torrents." | tee -a $logFile
  qbt torrent force-resume ALL
}

function forceResumeMover() {
  checkSettings
  # Initialize variables
  moverCount=0
  let min=sleepDuration/60
  while true; do
    echo -e "Checking UnRAID Log"
    log=$(ssh $remote_host "cat /var/log/syslog" | tail -n $logLineTail)
    if echo "$log" | grep -q "exit.*/usr/local/sbin/mover"; then
        echo -e "$(dateFormat) ${INFO} Mover has stopped running." | tee -a $logFile
        echo -e "$(dateFormat) ${INFO} Force resuming ALL torrents" | tee -a $logFile
        qbt torrent force-resume ALL
        break
    fi
    let countRemaining=countMax-moverCount
    let totaltime=countRemaining*min
    let moverCount+=1
    if [ $moverCount -eq $countMax ]; then
        echo -e "$(dateFormat) ${WARN} Mover is still running. Stopping Mover." | tee -a $logFile
        echo -e "$(dateFormat) ${INFO} Force resuming ALL torrents." | tee -a $logFile
        ssh $remote_host "mover stop"
        sleep 5
        qbt torrent force-resume ALL
        break
    fi
    echo -e "$(dateFormat) ${WARN} Mover is still running." | tee -a $logFile
    echo -e "$(dateFormat) ${INFO} Sleeping for $min minutes." | tee -a $logFile
    echo -e "$(dateFormat) ${INFO} Will retry $countRemaining more times (ETA: $totaltime minutes)." | tee -a $logFile
    sleep $sleepDuration
  done
}

function pause() {
  checkSettings
  qbt torrent list -F json > $jsonFilename
  echo -e "$(dateFormat) ${INFO} JSON file exported successfully" | tee -a $logFile
  #parse json file and find all torrents with "state"
  hashes=""
  for state in "${states[@]}"; do
    hashes="$hashes $(jq -r '.[] | select(.state=="'$state'") | .hash' $jsonFilename)"
  done
  # loop through each hash and pause the corresponding torrent
  for hash in $hashes; do
    name=$(jq -r '.[] | select(.hash=="'$hash'") | .name' $jsonFilename)
    qbt torrent pause $hash
    echo -e "$(dateFormat) ${INFO} Torrent Paused: Hash ${teal}${hash:0:5}${reset} :: Name $name" | tee -a $logFile
  done
  rm -f $jsonFilename
}

#### CRON functions

function cronHelp(){
    echo -e "${teal}$Name${reset} | ${yellow}Version:${reset} $version | ${red}Repo:${reset} https://github.com/jarsky/qbt-mover

    Usage $0 -cron [command] [arg]
    all                    Will add all cron entries
    pause                  Will add cron entry for pausing
    force-resume           Will add cron entry for force-resuming
    force-resume mover     Will add cron entry for force-resuming mover
    remove                 Will delete all cron entries"
    echo -e ""
}

function confirmCronJob() {
    read -p "Are you sure you want to add/remove a CRON job for $cronuser? (Y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "$(dateFormat) ${ERROR} CRON Job creation/removal cancelled by user" | tee -a $logFile
        exit 1
    fi
}

function createCronJob(){
    checkSettings
    if [[ -z `crontab -l | grep "## qbt-mover"` ]]; then
        (crontab -l 2>/dev/null; echo "## qbt-mover cron") | crontab -
    fi
    if [[ -z `crontab -l | grep "qbt-mover.*$1"` ]]; then
        (crontab -l 2>/dev/null; echo "35 3 * * *      cd $current_dir && ./qbt-mover.sh $2") | crontab -
        echo -e "$(dateFormat) ${INFO} CRON Job [$1] created for $cronuser" | tee -a $logFile
    else echo -e "$(dateFormat) ${INFO} CRON Job [$1] already exists for $cronuser" | tee -a $logFile
    fi
}

function removeCronJob(){
    checkSettings
    cronjobs=$(crontab -l | grep "qbt-mover")
    if [[ -z $cronjobs ]]; then
        echo -e "$(dateFormat) ${ERROR} CRON No qbt-mover jobs found for $cronuser" | tee -a $logFile
    else
        crontab -l | grep -v "qbt-mover" | crontab -
        echo -e "$(dateFormat) ${INFO} CRON All qbt-mover jobs have been removed from $cronuser" | tee -a $logFile
    fi
}

### Script

    if [[ $# -eq 0 ]]; then
        echo -e "$(dateFormat) ${WARN} No command was defined."
        echo -e "$(dateFormat) ${INFO} You need to enter a command. for a list use $0 --help"
        exit 1
    fi

    if [[ $1 == "-h" || $1 == "--help" ]]; then
        helpCMD
    elif [[ $1 == "-v" || $1 == "--version" ]]; then
        versionCMD
    elif [[ $1 == "-force-resume" ]]; then
        if [[ $2 == "mover" ]]; then
            forceResumeMover
        else
            forceResume
        fi
    elif [[ $1 == "-pause" ]]; then
            checkSettings
            pause
    elif [[ $1 == "-cron" ]]; then
        current_dir=$(pwd)
        cronuser=${teal}$(whoami)${reset}
        argError="$(dateFormat) ${ERROR} ${red}Invalid Argument '$2' ${reset}: Check your syntax. Use --help for a list"
        if [[ $# -eq 1 ]]; then
            cronHelp
        elif [[ $2 != "all" ]] && [[ $2 != "pause" ]] && [[ $2 != "force-resume" ]] && [[ $2 != "remove" ]]; then
            echo -e $argError
            exit 1
        fi
        if [[ $2 == "all" ]]; then
            confirmCronJob
            createCronJob "pause" "-pause"
            createCronJob "force-resume mover" "-force-resume mover"
        elif [[ $2 == "pause" ]]; then
            confirmCronJob
            createCronJob "pause" "-pause"
        elif [[ $2 == "force-resume" ]]; then
            if [[ $3 == "mover" ]]; then
                confirmCronJob
                createCronJob "force-resume mover" "-force-resume mover"
            else
                confirmCronJob
                createCronJob "force-resume" "-force-resume"
            fi
        elif [[ $2 == "remove" ]]; then
            confirmCronJob
            removeCronJob
    fi
fi
