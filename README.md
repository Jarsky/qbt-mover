
# qBt-mover

qBt-mover  is a script for qBittorrent CLI and UnRAID.
qBittorrent CLI is a command line interface to connect to the web socket for managing qBittorrent.

This is useful for automation being able to create scripts and interface with the qBitTorrent web API using qBittorrent CLI.

You can get qBittorrent CLI from https://github.com/fedarovich/qbittorrent-cli  
See their WIKI for more info: https://github.com/fedarovich/qbittorrent-cli/wiki

## Why?

qBitTorrent locks files that are active.  
If you're using the Cache in UnRAID, when the daily mover runs to move the files to the array, 
if the files are seeding then the mover will be unable to move them.

This script is to Pause the torrents before the Mover is scheduled to run.  
It will then check if the Mover has stopped to Force-Resume the torrents.  
It will keep checking for a user defined amount of time and then stop the mover and start torrents.


## Installation

Install qbittorrent-cli  

Install jq (JSON processor)

```bash
sudo apt update && sudo apt install -y jq
```

Clone qbt-mover 

```bash
  git clone https://github.com/Jarsky/qbt-mover.git && chmod +x ./qbt-mover/qbt-mover.sh
```

Or wget the qbt-mover.sh file

```bash
wget https://raw.githubusercontent.com/Jarsky/qbt-mover/main/qbt-mover.sh && chmod +x ./qbt-mover.sh
```

Configure defaults for qbittorrent-cli

```bash
qbt settings set url http://localhost:8000 #URL of qBitTorrent WebUI
qbt settings set username <username> #Only if you enabled user authentication
qbt settings set password <prompt> #Only if you enabled user authentication
```

Setup SSH Key access to your UnRAID  

**Note**: If you want to use root for everything, run these with sudo.

```bash
# Generate an SSH Key on the qbt-cli / qbt-mover machine (Enter through)
    ssh-keygen -t rsa -b 4096 -C "your_email@domain.com"
# Upload the SSH Public Key to your UnRAID Server
    ssh-copy-id root@tower

```
Test SSH Key works:  
```bash
ssh root@tower
```


## Usage


### General

If you execute ./qbt-mover.sh it will give you guidance  
You can use ./qbt-mover.sh --help for supported commands  

![Screenshot](https://i.gyazo.com/0a811a25be40647dadbe9e193b011c14.png)
  
The "mover" function will check if the UnRAID mover has finished.  
If not the script will sleep for a period of time and check again.  

After a user defined number of attempts, it will issue a stop command to UnRAID  
and start the qBittorrent torrents.  
  
**NOTE**: Because the script checks a number of times, it can be scheduled for right  
after the Mover starts. The script will _not_ start the torrents until the mover has finished  
or approx 45 minutes with the default config. 

### CRON  
  
qBt-mover can setup CRON for you.  
Simply run ./qbt-mover.sh -cron which will give you the commands. 

![Screenshot](https://i.gyazo.com/422f8a87bb4b55aba954f263a3a3db7e.png)

By default UnRAID runs its Mover at 3:40AM daily.  
qBt-mover defaults:  
  3:35AM for Torrent Pause  
  3:45AM for Torrent Start  
  
Setting up the default using **./qbt-mover.sh -cron all** looks like below

```bash
## qbt-mover cron
35 3 * * *      cd /home/jarsky/scripts/qbt-mover && ./qbt-mover.sh -pause
45 3 * * *      cd /home/jarsky/scripts/qbt-mover && ./qbt-mover.sh -force-resume mover
```

If you aren't using UnRAID, then you could just add pause and force-resume 

```bash
./qbt-mover.sh -cron pause
./qbt-mover.sh -cron force-resume
```

If you want to remove the CRON entries just use

```bash
./qbt-mover.sh -cron remove
```

### LOGGING

**Default:** /var/log/qbt-mover.log

If you want to run the script as your user in this location, then:

```bash
sudo touch /var/log/qbt-mover.log
sudo chmod 755 /var/log/qbt-mover.log
```


It is good practice to configure a logrotate.  
In most GNU you would do something like this

```bash
sudo touch /etc/logrotate.d/qbt-mover
sudo nano /etc/logrotate.d/qbt-mover
```

And put the below code into the file and save

```bash
    /var/log/qbt-mover.log {
            size 2M
            rotate 5
            compress
            delaycompress
            missingok
            notifempty
    }
```

This will let the log grow to 2Megabytes, then rotate. It will rotate 5x and then delete the oldest.  
The log files from 2 onwards will be compressed.  

You can run do a dry-run by running this command

```bash
sudo logrotate -d /etc/logrotate.d/qbt-mover
```

