
#     qBt-mover script by Jarsky
    v1.2  15/01/2023



This is a script for qBittorrent CLI and UnRAID. 
qBittorrent CLI is a command line interface to connect to the web socket for managing qBittorrent. 

This is useful for automation being able to create scripts and interface with the qBitTorrent web API using qBittorrent CLI.

You can get qBittorrent CLI from https://github.com/fedarovich/qbittorrent-cli
See their WIKI for more info: https://github.com/fedarovich/qbittorrent-cli/wiki




## WHY?

qBitTorrent locks files that are active. If you're using the Cache in UnRAID, when the daily mover
runs to move the files to the array, if the files are seeding then the mover will be unable to move them. 

This script is to Pause the torrents before the Mover is scheduled to run. 
It will then check if the Mover has stopped to Force-Resume the torrents.
It will keep checking for a user defined amount of time and then stop the mover and start torrents.



## General setup:
---------------

```console
qbt settings set url http://localhost:8000
qbt settings set username admin
qbt settings set password <prompt>
```


This will generate a settings.json file located at ~/.qbt/settings.json

If you are running CRON jobs or scripts with another user e.g sudo 
Then you will either need to configure settings as sudo (e.g sudo qbt settings set)
or you will need to copy the settings (i.e sudo cp -R ~/.qbt/ /root/.qbt/)


## CRON
-----------

The script can automatically setup CRON using ./qbt-mover.sh -cron
By default the UnRAID mover runs at 3:40AM daily.

CRON jobs are standard. 
Setup Example:

#### Will run to pause torrents at 4:58am every day
Will run to resume torrents at 5:05am every day. Checking the UnRAID mover before resuming

```console
## qbt-mover cron
35 3 * * *      cd /home/ubuntu/scripts/qbt-mover && ./qbt-mover.sh -pause
45 3 * * *      cd /home/ubuntu/scripts/qbt-mover && ./qbt-mover.sh -force-resume mover
```


You can edit the CRON entry to suit if you have changed your mover schedule. 
You can schedule the -force-resume mover straight away after the mover as it tries for roughly
45 minutes with the default settings if the mover is still running. 


# LOGS
----------

By default the script logs to: /var/log/qbt-mover.log

It is good practice to configure a logrotate. 
That might look something like this:

```console
sudo touch /etc/logrotate.d/qbt-mover
sudo nano /etc/logrotate.d/qbt-mover
```

#This example will set max size 2Megabytes then rotate, It will compress logs from the second 
#and it will allow up to 5 rotates and then delete the oldest. 

```console
    /var/log/qbt-mover.log {
            size 2M
            rotate 5
            compress
            delaycompress
            missingok
            notifempty
    }
```

You can test using:

```console
sudo logrotate -d /etc/logrotate.d/qbt-mover
```

