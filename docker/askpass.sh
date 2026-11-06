#!/bin/sh
# Gives ssh the key passphrase. ssh is limited to publickey auth, so this answers nothing else.
exec cat /run/qbt-mover/ssh_passphrase
