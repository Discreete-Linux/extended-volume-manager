#!/usr/bin/python3
# Encoding: UTF-8

import os
import syslog
import sys
import time
import signal
import subprocess
import getopt
import tempfile
import daemon
import lockfile

target = os.getcwd()

def _write_dump(arg1=None, arg2=None):
    global target
    gconfdumps = ("/apps/evolution", "/apps/hamster-applet", "/apps/hamster-indicator",
                  "/apps/planner", "/desktop/gnome/keybindings", "/apps/metacity", "/apps/gthumb")
    dconfdumps = ("/apps/seahorse", "/org/gnome/nautilus",
                  "/org/gnome/settings-daemon/plugins/power",
                  "/org/gnome/desktop/session", "/org/gnome/settings-daemon/peripherals/mouse",
                  "/org/gnome/settings-daemon/peripherals/touchpad",
                  "/org/gnome/settings-daemon/peripherals/keyboard",
                  "/apps/onboard", "/org/gnome/libgnomekbd",
                  "/org/freedesktop/tracker")

    syslog.syslog(syslog.LOG_DEBUG, "Saving GConf data.")
    for gconfdump in gconfdumps:
        try:
            dumpfile = open("%s/.%s-backup.xml.dump" % (target, gconfdump.rsplit('/', 1)[1]), 'w')
            subprocess.call(["/usr/bin/gconftool-2", "--dump", "%s" % gconfdump], stdout=dumpfile)
            dumpfile.close()
        except:
            syslog.syslog(syslog.LOG_ERR, "Error occured trying to write to %s: %s" % \
                          (dumpfile, str(sys.exc_info())))
    for dconfdump in dconfdumps:
        try:
            dumpfile = open("%s/.%s-backup.txt.dump" % (target, dconfdump.rsplit('/', 1)[1]), 'w')
            subprocess.call(["/usr/bin/dconf", "dump", "%s/" % dconfdump], stdout=dumpfile)
            dumpfile.close()
        except:
            syslog.syslog(syslog.LOG_ERR, "Error occured trying to write to %s: %s" % \
                          (dumpfile, str(sys.exc_info())))

def main_loop():
    while True:
        _write_dump()
        time.sleep(300)

def do_quit(arg1=None, arg2=None):
    _write_dump()
    if os.path.exists("%s/.gconf-dumper" % os.environ["HOME"]):
        os.remove("%s/.gconf-dumper" % os.environ["HOME"])
    exit(0)

def main():
    global target
    syslog.openlog("extended-volume-manager")
    action = "start"
    try:
        opts, unknown = getopt.getopt(sys.argv[1:], "rqt:")
    except getopt.GetoptError:
        pass
    for o, a in opts:
        if o == "-t":
            target = a.rstrip('/')
        elif o == "-r":
            action = "start"
        elif o == "-q":
            action = "stop"
    if len(unknown) > 0:
        syslog.syslog(syslog.LOG_DEBUG, "Unknown options passed, ignoring: %s" % str(unknown))
    if action == "stop":
        args = ["ps", "-o", "pid", "-C", "gconf-dumper.py", "--no-headers"]
        ps = subprocess.Popen(args, stdout=subprocess.PIPE)
        for line in ps.stdout.readlines():
            os.kill(int(line.strip()), signal.SIGTERM)
        ps.stdout.close()
    else:
        if not os.path.isdir(target):
            syslog.syslog(syslog.LOG_ERR, "Target is not a directory")
            exit(1)
        context = daemon.DaemonContext()
        context.working_directory = tempfile.gettempdir()
        context.pidfile = lockfile.FileLock("%s/.gconf-dumper" % tempfile.gettempdir())
        context.signal_map = {
            signal.SIGTERM: do_quit,
            signal.SIGHUP: 'terminate',
            signal.SIGUSR1: _write_dump,
            }
        with context:
            main_loop()

if __name__ == "__main__":
    main()
