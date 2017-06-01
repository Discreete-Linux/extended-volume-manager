#!/usr/bin/python
# Encoding: UTF-8
""" Handle opening/closing of extended volumes """

import os
import subprocess
import gettext
import traceback
import sys
import time
import re
import syslog
import glob
import shutil
import threading
import multiprocessing
import pickle
import cups
import pyudev
import truecrypthelper
try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Notify, GLib, Gio
except:
    pass

try:
    from vboxapi import VirtualBoxManager
except:
    pass
import fileutils

gettext.install("extended-volume-manager", unicode=1)
Notify.init("extended-volume-manager")
pyn = Notify.Notification()
pyn.set_urgency(Notify.Urgency.NORMAL)
pyn.set_app_name("extended-volume-manager")
pyn.set_category("device")
pyn.set_hint("transient", GLib.Variant('b', True))
pyn.set_timeout(2000)
syslog.openlog("extended-volume-manager")

class PBarThread(threading.Thread):
    def __init__(self, title, message):
        super(PBarThread, self).__init__()
        self._stop = threading.Event()
        self.win = Gtk.Window()
        self.vbox = Gtk.VBox(homogeneous=True, spacing=10)
        self.label = Gtk.Label(label=message)
        self.pbar = Gtk.ProgressBar()
        self.vbox.pack_start(self.label, True, True, 0)
        self.vbox.pack_start(self.pbar, True, True, 0)
        self.win.add(self.vbox)
        self.win.set_position(Gtk.WindowPosition.CENTER)
        self.win.set_border_width(10)
        self.win.set_keep_above(True)
        self.win.set_title(title)

    def run(self):
        self.win.show_all()
        while not self.stopped():
            self.pbar.pulse()
            while Gtk.events_pending():
                Gtk.main_iteration()
            time.sleep(.25)
        self.win.destroy()
        while Gtk.events_pending():
            Gtk.main_iteration()

    def stop(self):
        self._stop.set()

    def stopped(self):
        return self._stop.isSet()

def _double_fork(cmd):
    """ Execute child process with double fork. """
    args = "import subprocess\nsubprocess.Popen(" +str(cmd) + ")"
    subprocess.Popen(["/usr/bin/python", "-c", args])

def start_with_pbar(args, title, message):
    win = Gtk.Window()
    vbox = Gtk.VBox(homogeneous=True, spacing=10)
    label = Gtk.Label(label=message)
    pbar = Gtk.ProgressBar()
    vbox.pack_start(label, True, True, 0)
    vbox.pack_start(pbar, True, True, 0)
    win.add(vbox)
    win.set_position(Gtk.WindowPosition.CENTER)
    win.set_border_width(10)
    win.set_keep_above(True)
    win.set_title(title)
    win.show_all()
    p = multiprocessing.Process(target=subprocess.call, args=(args,))
    p.start()
    while p.is_alive():
        pbar.pulse()
        while Gtk.events_pending():
            Gtk.main_iteration()
        time.sleep(.25)
    win.destroy()
    while Gtk.events_pending():
        Gtk.main_iteration()
    p.join()
    return p.exitcode

def show_error(message=None, variables=None):
    """ Display error messages """
    if message is None:
        syslog.syslog("Error: %s; Vars: %s" % (traceback.format_exc(), str(variables)))
        message = _("A system error occured. The error was\n\n%(error)s\n\nLocal variables:\n%(vars)s") % {"error":traceback.format_exc(), "vars":str(variables)}
    else:
        syslog.syslog(message.encode('ascii', 'replace'))
    dlg = Gtk.MessageDialog(type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK)
    dlg.format_secondary_text(message)
    dlg.run()
    dlg.destroy()
    while Gtk.events_pending():
        Gtk.main_iteration()
    return

def ask_user(title, message):
    question = Gtk.MessageDialog(buttons=Gtk.ButtonsType.YES_NO, type=Gtk.MessageType.QUESTION)
    question.set_markup(_(message))
    question.set_title(title)
    question.set_default_response(Gtk.ResponseType.YES)
    question.set_urgency_hint(True)
    question.set_keep_above(True)
    response = question.run()
    question.destroy()
    while Gtk.events_pending():
        Gtk.main_iteration()
    return response == Gtk.ResponseType.YES

def _getUSBStorageList():
    """ Get the list of USB storage device files """
    usbList = list()
    context = pyudev.Context()
    for device in context.list_devices(subsystem='block', ID_BUS='usb'):
        if device.device_type == "disk" or device.device_type == "sd_mmc":
            usbList.append(device.device_node)
    return usbList

def getFilesystem(path):
    """ Return the filesystem of a mounted volume. """
    if not os.path.exists(path):
        return None
    fs = None
    try:
        while not os.path.ismount(path):
            path = os.path.split(path)[0]
        p = open('/proc/mounts', 'r')
        proc = p.readlines()
        p.close()
        fs = re.search("^[-/a-zA-Z0-9]* " + path + " ([a-zA-Z0-9]+)",
                       ''.join(proc), re.MULTILINE).group(1)
    except:
        pass
    return fs
    
def fixPermissions(path):
    try:
        syslog.syslog(syslog.LOG_DEBUG, "Setting permissions on %s" % path)
        subprocess.call(["/usr/bin/sudo", "/bin/chown", "-R",
                         "%s:%s" % (str(os.getuid()), str(os.getgid())), path])
        subprocess.call(["/usr/bin/sudo", "/bin/chmod", "-R", "a+rwX", path])
    except:
        show_error(_("Could not set permissions and/or ownership on %s") % path)

def _is_backup_device(device):
    args = ["/usr/bin/sudo", "/usr/bin/tc-backup-signature", device]
    prog = subprocess.Popen(args)
    ret = prog.wait()
    return ret == 0

def is_backup_device(devfile):
    return _is_backup_device(devfile.rstrip("0123456789"))

def _find_backup_devices():
    """ Find all backup devices """
    deviceList = list()
    for device in _getUSBStorageList():
        if _is_backup_device(device):
            deviceList.append(device + "1")
    return deviceList

def _find_backup_containers():
    """ Find all backup container files """
    return glob.glob(u"/media/*/backup.tc")

def _open_backup_container(mountpoint):
    """ Find and open a backup container

    Return mount point if backup container was successfully opened.
    """
    syslog.syslog(syslog.LOG_DEBUG, "Looking for backup container")
    if mountpoint == "/media/backup":
        syslog.syslog(syslog.LOG_DEBUG, "The backup container is the current "
                                        "container, skipping backup.")
        return False
    if os.path.exists("/media/backup") and os.path.ismount("/media/backup"):
        syslog.syslog(syslog.LOG_DEBUG, "Found already mounted backup "
                                        "volume/container at /media/backup")
        if ask_user(_('Do you want to da a backup?'),
                    _("It looks like you have a backup container/volume mounted "
                      "at /media/backup. Do you want to use it for a backup of "
                      "your files in %s?") % mountpoint):
            return "/media/backup"
        else:
            return False
    backupcont = _find_backup_containers()
    backupcont += _find_backup_devices()
    if len(backupcont) == 0:
        syslog.syslog(syslog.LOG_DEBUG, "No backup container found")
        return False
    elif len(backupcont) > 1:
        message = _("More than one possible backup container or device was found. "
                    "Automatic backup cannot continue. Please make sure only one "
                    "backup container or device is present.\n\nI have found these "
                    "containers and devices:\n")
        message += '\n'.join(backupcont)
        show_error(message)
        return False
    syslog.syslog(syslog.LOG_DEBUG, "Backup container found, asking user")
    if not ask_user(_('Do you want to da a backup?'),
                    _('%(backupname)s looks like an encrypted backup container. '
                      'Do you want to use it for a backup of your files in %(origname)s? '
                      'If you answer with \"OK\", you will have to enter the password '
                      'for %(backupname)s in the next step.') % \
                      {"backupname": backupcont[0], "origname": mountpoint}):
        syslog.syslog(syslog.LOG_DEBUG, "User cancelled backup")
        return False
    if not truecrypthelper.tc_open(backupcont[0]):
        syslog.syslog(syslog.LOG_DEBUG, "User cancelled opening backup container")
        return False
    backupfs = getFilesystem("/media/backup")
    if "ext" not in backupfs:
        show_error(_("%(backupname)s is not an \"extended volume\" and can therefore "
                     "not be used for a backup.\nPlease convert %(backupname)s to an "
                     "\"extended Volume\" or create a new, ext3 formatted backup volume "
                     "with name backup.tc." % {"backupname": backupcont[0]}))
        subprocess.call(["umount", "/media/backup"])
        return False
    return "/media/backup"

def _close_backup_container(backupmp):
    """ Close an open backup container """
    syslog.syslog(syslog.LOG_DEBUG, "Closing backup container")
    start_with_pbar(["/bin/sync"], _("Unmounting"), _("Please wait until all data "
                                                      "has been written to disk..."))
    subprocess.call(["umount", backupmp])

def _do_backup(mountpoint, backupmp):
    """ Do a backup of mountpoint to backup container """
    global pyn
    syslog.syslog(syslog.LOG_DEBUG,
                  "Starting backup of %s" % mountpoint.encode('ascii', 'replace'))
    mountpoint = mountpoint.rstrip('/')
    backupdir = backupmp + "/" + os.path.basename(mountpoint) + "-Backup"
    backupcur = backupdir + "/Backup_" + time.strftime("%y.%m.%d_%H%M")
    try:
        if not os.path.exists(backupdir):
            os.makedirs(backupdir)
        backuplist = os.listdir(backupdir)
        backuplist.sort()
        os.makedirs(backupcur)
    except:
        show_error(_("An error occured during backup!\nCould not create target directory."))
        return False
    #  If no backup exists yet, start this backup with a progress bar
    if len(backuplist) == 0:
        syslog.syslog(syslog.LOG_DEBUG, "Doing initial backup")
        args = ["gtkrsync", "--progress", "-vrltD", "--delete", "--delete-before",
                "--no-inc-recursive", mountpoint + "/", backupcur]
    else:
        syslog.syslog(syslog.LOG_DEBUG, "Doing incremental backup")
        args = ["/usr/bin/gtkrsync", "--progress", "-vrltD", "--delete",
                "--delete-before", "--no-inc-recursive", "--link-dest=%s" % \
                backupdir + "/" + backuplist[-1], mountpoint + "/", backupcur]
    syslog.syslog(syslog.LOG_DEBUG, "Calling rsync...")
    try:
        ret = subprocess.call(args)
    except:
        show_error(_("An error occured during backup. Error occured while executing gtkrsync!"))
        return False
    syslog.syslog(syslog.LOG_DEBUG, "Rsync returned %i" % ret)
    if ret == 20:
        syslog.syslog(syslog.LOG_DEBUG, "Rsync was cancelled, deleting current backup")
        try:
            shutil.rmtree(backupcur)
        except:
            show_error(_("Could not delete incomplete backup at %s") % backupcur)
            return False
        return False
    elif ret == 0 or ret == 24:
        syslog.syslog(syslog.LOG_DEBUG, "Backup successful, removing old backups.")
        pb = PBarThread(_("Cleaning up"), _("Old backups are being cleaned up, please wait..."))
        pb.start()
        while len(backuplist) > 4:
            oldbackup = backupdir + "/" + backuplist.pop(0)
            try:
                shutil.rmtree(oldbackup)
            except:
                show_error(_("Could not delete old backup at %s") % oldbackup)
        pb.stop()
        pb.join()
        pyn.update(_("Backup done."), \
                        _("Backup of %s successful.") % mountpoint, "usbpendrive_unmount")
        pyn.show()
        syslog.syslog(syslog.LOG_DEBUG, "All old backups removed")
    else:
        show_error(_("An error occured during backup!\nMaybe there is not enough "
                     "space at the destination."))
        try:
            shutil.rmtree(backupcur)
        except:
            show_error(_("Could not delete incomplete backup at %s") % backupcur)
            return False
        return False
    return True

def _backup_other_containers(exttcdev, backupmp):
    """ Does a backup of other open containers into the same backup container """
    # TODO: needs re-implementation
    syslog.syslog(syslog.LOG_DEBUG, "Looking for other containers to back up")
    backup_others = ""

    # Build a x*4 list of open TrueCrypt volumes, with
    # tclist[x][0] = Slot number
    # tclist[x][1] = filename
    # tclist[x][2] = dm_device
    # tclist[x][3] = mountpoint
    tclines = subprocess.Popen(truecrypthelper.tct + ["-l"], \
              stdout=subprocess.PIPE).communicate()[0]
    p = re.findall("^([0-9]{1,2}): ((?:\'[^\']+\')|\S+) (\S+) ((?:\'[^\']+\')|\S+)",
                   tclines, re.MULTILINE)
    tclist = [[filter(lambda c: c not in "'", m) for m in i] for i in p]

    for tcitem in tclist:
        if (tcitem[2] == exttcdev) or (tcitem[3] == backupmp):
            continue
        target_mp = tcitem[3].decode('utf-8', 'replace')
        syslog.syslog(syslog.LOG_DEBUG, "Found another container at %s" % target_mp)
        if backup_others != "Yes":
            s = os.statvfs(backupmp)
            df = (s.f_bavail * s.f_frsize)
            humanreadable = lambda s: [(s%1024**i and "%.1f"%(s/1024.0**i) or
                                        str(s/1024**i))+x.strip() for i, x in
                                       enumerate(' KMGTPEZY') if s < 1024**(i+1) or i == 8][0]
            if ask_user(_("Backup other containers?"),
                        _("You can now backup your other open containers as well. "
                          "Their contents will be stored within the same backup "
                          "container, but in a separate directory. Do you want to "
                          "do this now?\n\nHint: The backup container has %s free space.") % \
                          humanreadable(df)):
                backup_others = "Yes"
            else:
                syslog.syslog(syslog.LOG_DEBUG, "User decided against backup")
                return False
        if backup_others == "Yes":
            _do_backup(target_mp, backupmp)
            subprocess.call(["umount", target_mp])

def _link_confdir(mountpoint, confdir):
    try:
        syslog.syslog(syslog.LOG_DEBUG, "Configuration directory %s" % confdir)
        if not os.path.exists(os.path.join(mountpoint, confdir)):
            fileutils.mkdir_p(os.path.join(mountpoint, confdir))
        if not os.path.exists(os.path.join(os.environ["HOME"], os.path.dirname(confdir))):
            fileutils.mkdir_p(os.path.join(os.environ["HOME"], os.path.dirname(confdir)))
        if os.path.lexists(os.path.join(os.environ["HOME"], confdir)):
            if os.path.lexists(os.path.join(os.environ["HOME"], confdir + ".old")):
                i = 2
                while os.path.lexists(os.path.join(os.environ["HOME"], confdir + ".old-" + str(i))):
                    i = i+1
                os.rename(os.path.join(os.environ["HOME"], confdir + ".old"),
                          os.path.join(os.environ["HOME"], confdir + ".old-" + str(i)))
            os.rename(os.path.join(os.environ["HOME"], confdir),
                      os.path.join(os.environ["HOME"], confdir + ".old"))
        os.symlink(os.path.join(mountpoint, confdir), os.path.join(os.environ["HOME"], confdir))
    except:
        show_error(variables=vars())
        return False

def _unlink_confdir(mountpoint, confdir):
    syslog.syslog(syslog.LOG_DEBUG, "Configuration directory %s" % confdir)
    try:
        if os.path.islink(os.path.join(os.environ["HOME"], confdir)):
            os.remove(os.path.join(os.environ["HOME"], confdir))
        if os.path.exists(os.path.join(os.environ["HOME"], confdir + ".old")):
            os.rename(os.path.join(os.environ["HOME"], confdir + ".old"),
                      os.path.join(os.environ["HOME"], confdir))
    except:
        show_error(variables=vars())
        return False

def _link_conffile(mountpoint, conffile):
    destfile = os.path.basename(conffile)
    if not destfile.startswith('.'):
        destfile = '.' + destfile
    try:
        syslog.syslog(syslog.LOG_DEBUG, "Configuration file %s" % conffile)
        if not os.path.exists(os.path.join(mountpoint, destfile)):
            os.mknod(os.path.join(mountpoint.encode('utf-8'), destfile))
        if not os.path.exists(os.path.join(os.environ["HOME"], os.path.dirname(conffile))):
            fileutils.mkdir_p(os.path.join(os.environ["HOME"], os.path.dirname(conffile)))
        if os.path.lexists(os.path.join(os.environ["HOME"], conffile)):
            if os.path.exists(os.path.join(os.environ["HOME"], conffile + ".old")):
                i = 2
                while os.path.exists(os.path.join(os.environ["HOME"], conffile + ".old-" + str(i))):
                    i = i+1
                os.rename(os.path.join(os.environ["HOME"], conffile + ".old"),
                          os.path.join % (os.environ["HOME"], conffile + ".old-" + str(i)))
            os.rename(os.path.join(os.environ["HOME"], conffile),
                      os.path.join(os.environ["HOME"], conffile + ".old"))
        os.symlink(os.path.join(mountpoint, destfile), os.path.join(os.environ["HOME"], conffile))
    except:
        show_error(variables=vars())
        return False

def _unlink_conffile(mountpoint, conffile):
    syslog.syslog(syslog.LOG_DEBUG, "Configuration file %s" % conffile)
    try:
        if os.path.islink(os.path.join(os.environ["HOME"], conffile)):
            os.remove(os.path.join(os.environ["HOME"], conffile))
        if os.path.exists(os.path.join(os.environ["HOME"], conffile + ".old")):
            os.rename(os.path.join(os.environ["HOME"], conffile + ".old"),
                      os.path.join(os.environ["HOME"], conffile))
    except:
        show_error(variables=vars())
        return False

def _load_gconf(mountpoint, gconfkey):
    try:
        if os.path.exists("%s/.%s-backup.xml.dump" % (mountpoint, gconfkey.rsplit('/', 1)[1])):
            syslog.syslog(syslog.LOG_DEBUG, "GConf key %s" % gconfkey)
            subprocess.call(["/usr/bin/gconftool-2", "--load",
                             "%s/.%s-backup.xml.dump" % (mountpoint, gconfkey.rsplit('/', 1)[1])])
    except:
        show_error(variables=vars())
        return False

def _save_gconf(mountpoint, gconfkey):
    try:
        dumpfile = open("%s/.%s-backup.xml.dump" % (mountpoint, gconfkey.rsplit('/', 1)[1]), 'w')
        syslog.syslog(syslog.LOG_DEBUG, "GConf key %s" % gconfkey)
        subprocess.call(["/usr/bin/gconftool-2", "--dump", "%s" % gconfkey], stdout=dumpfile)
        dumpfile.close()
    except:
        show_error(variables=vars())
        return False

def _load_dconf(mountpoint, dconfkey):
    dconfkey = dconfkey.rstrip('/')
    try:
        if os.path.exists("%s/.%s-backup.txt.dump" % (mountpoint, dconfkey.rsplit('/', 1)[1])):
            syslog.syslog(syslog.LOG_DEBUG, "DConf key %s" % dconfkey)
            subprocess.call(["/usr/bin/dconf", "load", "%s/" % dconfkey],
                            stdin=open("%s/.%s-backup.txt.dump" % \
                            (mountpoint, dconfkey.rsplit('/', 1)[1]), 'r'))
    except:
        show_error(variables=vars())
        return False

def _save_dconf(mountpoint, dconfkey):
    dconfkey = dconfkey.rstrip('/')
    try:
        dumpfile = open("%s/.%s-backup.txt.dump" % (mountpoint, dconfkey.rsplit('/', 1)[1]), 'w')
        syslog.syslog(syslog.LOG_DEBUG, "DConf key %s" % dconfkey)
        subprocess.call(["/usr/bin/dconf", "dump", "%s/" % dconfkey], stdout=dumpfile)
        dumpfile.close()
    except:
        show_error(variables=vars())
        return False

def _migrate_confdir(mountpoint, oldpath, newpath):
    try:
        if os.path.exists(os.path.join(mountpoint, oldpath)):
            if not os.path.exists(os.path.join(mountpoint, newpath)):
                syslog.syslog(syslog.LOG_DEBUG,
                              "Migrating old directory %s to new directory %s" % (oldpath, newpath))
                shutil.copytree(os.path.join(mountpoint, oldpath), os.path.join(mountpoint, newpath))
    except:
        return False

def _open_gnupg(mountpoint):
    _link_confdir(mountpoint, ".gnupg")
    _load_dconf(mountpoint, "/apps/seahorse")
    try:
        if os.path.exists(mountpoint + "/.gnupg"):
            syslog.syslog(syslog.LOG_DEBUG, "Setting permissions on .gnupg")
            fileutils.chmod_R("0700", mountpoint + "/.gnupg")
        if not os.path.exists(mountpoint + "/.gnupg/gnupg-scripts.conf"):
            syslog.syslog(syslog.LOG_DEBUG, "Creating gnupg-scripts default configuration")
            subprocess.call(["/usr/bin/gpg-config", "--default"])
    except:
        show_error(variables=vars())
        return False

def _close_gnupg(mountpoint):
    _save_dconf(mountpoint, "/apps/seahorse")
    _unlink_confdir(mountpoint, ".gnupg")
    try:
        syslog.syslog(syslog.LOG_DEBUG, "Reloading the gpg-agent")
        subprocess.call(["/usr/bin/pkill", "-HUP", "gpg-agent"])
    except:
        show_error(variables=vars())
        return False

def _really_kill_evolution():
    evoprocs = subprocess.Popen(["find", "/usr/lib/evolution", "-type", "f", "-and",
                                 "-executable", "-exec", "basename", "{}", ";"],
                                stdout=subprocess.PIPE).communicate()[0]
    evoprocs = evoprocs.replace('\n', ',') + 'evolution'
    evopids = subprocess.Popen(["ps", "-C", evoprocs, "-o", "pid", "--no-headers"],
                               stdout=subprocess.PIPE).communicate()[0]
    if len(evopids) == 0:
        return True
    evopids = evopids.strip().split('\n')
    for pid in evopids:
        subprocess.call(["kill", pid])
        subprocess.call(["kill", "-9", pid])
    evopids = subprocess.Popen(["ps", "-C", evoprocs, "-o", "pid", "--no-headers"],
                               stdout=subprocess.PIPE).communicate()[0]
    if len(evopids) > 0:
        return False
    else:
        return True

def _open_evolution(mountpoint):
    syslog.syslog(syslog.LOG_DEBUG, "Shutting down evolution")
    try:
        subprocess.call(["/usr/bin/evolution", "--force-shutdown"],
                        stdout=open(os.devnull, 'w'), stderr=subprocess.STDOUT)
    except:
        show_error(variables=vars())
        return False
    if not _really_kill_evolution():
        show_error(_("Failed to stop evolution, will skip loading evolution data "
                     "from the extended container!"))
    else:
        _link_confdir(mountpoint, ".local/share/evolution")
        _link_confdir(mountpoint, ".config/evolution")
        _link_confdir(mountpoint, ".cache/evolution")
        _load_gconf(mountpoint, "/apps/evolution")

def _close_evolution(mountpoint):
    syslog.syslog(syslog.LOG_DEBUG, "Shutting down evolution")
    try:
        subprocess.call(["/usr/bin/evolution", "--force-shutdown"],
                        stdout=open(os.devnull, 'w'), stderr=subprocess.STDOUT)
    except:
        show_error(variables=vars())
        return False
    _really_kill_evolution()
    _save_gconf(mountpoint, "/apps/evolution")
    _unlink_confdir(mountpoint, ".local/share/evolution")
    _unlink_confdir(mountpoint, ".config/evolution")
    _unlink_confdir(mountpoint, ".cache/evolution")

def _open_hamster(mountpoint):
    syslog.syslog(syslog.LOG_DEBUG, "Spawning the mighty hamster...")
    proclist = "hamster-service"
    pids = subprocess.Popen(["/bin/ps", "--no-headers", "-o", "pid", "-C", proclist],
                            stdout=subprocess.PIPE).communicate()[0]
    for pid in pids.split():
        try:
            subprocess.call(["kill", pid])
            subprocess.call(["kill", "-9", pid])
        except:
            pass
    _migrate_confdir(mountpoint, ".gnome2/hamster-applet", ".local/share/hamster-applet")
    _link_confdir(mountpoint, ".local/share/hamster-applet")
    _load_gconf(mountpoint, "/apps/hamster-applet")
    # _load_gconf(mountpoint, "/apps/hamster-indicator")
    subprocess.Popen(["/usr/lib/hamster-applet/hamster-service"])
    extlist = subprocess.Popen(["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
                               stdout=subprocess.PIPE).communicate()[0].strip('[').rstrip(']\n').split(', ')
    if "'hamster@projecthamster.wordpress.com'" not in extlist:
        extlist.append("'hamster@projecthamster.wordpress.com'")
        subprocess.call(["gsettings", "set", "org.gnome.shell", "enabled-extensions",
                         "[" + ', '.join(extlist) + "]"])

def _close_hamster(mountpoint):
    syslog.syslog(syslog.LOG_DEBUG, "Stopping hamster applet")
    _save_gconf(mountpoint, "/apps/hamster-applet")
    # _save_gconf(mountpoint, "/apps/hamster-indicator")
    _unlink_confdir(mountpoint, ".local/share/hamster-applet")
    proclist = "hamster-service"
    pids = subprocess.Popen(["/bin/ps", "--no-headers", "-o", "pid", "-C", proclist],
                            stdout=subprocess.PIPE).communicate()[0]
    for pid in pids.split():
        try:
            subprocess.call(["kill", pid])
            subprocess.call(["kill", "-9", pid])
        except:
            pass
    extlist = subprocess.Popen(["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
                               stdout=subprocess.PIPE).communicate()[0].strip('[').rstrip(']\n').split(', ')
    if "'hamster@projecthamster.wordpress.com'" in extlist:
        extlist = [x for x in extlist if x != "'hamster@projecthamster.wordpress.com'"]
        subprocess.call(["gsettings", "set", "org.gnome.shell", "enabled-extensions",
                         "[" + ', '.join(extlist) + "]"])

def _open_fpm(mountpoint):
    _link_confdir(mountpoint, ".fpm")

def _close_fpm(mountpoint):
    _unlink_confdir(mountpoint, ".fpm")

def _open_libreoffice(mountpoint):
    _migrate_confdir(mountpoint, ".openoffice.org", ".config/libreoffice")
    _link_confdir(mountpoint, ".config/libreoffice")
    _link_conffile(mountpoint, ".odbc.ini")

def _close_libreoffice(mountpoint):
    _unlink_confdir(mountpoint, ".config/libreoffice")
    _unlink_conffile(mountpoint, ".odbc.ini")

def _open_scribus(mountpoint):
    _link_confdir(mountpoint, ".scribus")

def _close_scribus(mountpoint):
    _unlink_confdir(mountpoint, ".scribus")

def _open_kmymoney(mountpoint):
    _link_conffile(mountpoint, ".kde/share/config/kmymoneyrc")

def _close_kmymoney(mountpoint):
    _unlink_conffile(mountpoint, ".kde/share/config/kmymoneyrc")

def _open_planner(mountpoint):
    _load_gconf(mountpoint, "/apps/planner")

def _close_planner(mountpoint):
    _save_gconf(mountpoint, "/apps/planner")

def _open_desktop(mountpoint):
    _load_dconf(mountpoint, "/org/gnome/settings-daemon/plugins/power")
    _load_dconf(mountpoint, "/org/gnome/desktop/session")
    _load_gconf(mountpoint, "/desktop/gnome/keybindings")
    _load_gconf(mountpoint, "/apps/metacity")
    _load_dconf(mountpoint, "/org/gnome/settings-daemon/peripherals/mouse")
    _load_dconf(mountpoint, "/org/gnome/settings-daemon/peripherals/touchpad")
    _load_dconf(mountpoint, "/org/gnome/settings-daemon/peripherals/keyboard")
    _migrate_confdir(mountpoint, ".fonts", ".local/share/fonts")
    _link_confdir(mountpoint, ".local/share/fonts")
    _link_conffile(mountpoint, ".gtk-bookmarks")
    _link_conffile(mountpoint, ".lockpasswd")
    _load_dconf(mountpoint, "/org/gnome/desktop/background")
    _load_dconf(mountpoint, "/org/gnome/nemo")
    _load_dconf(mountpoint, "/org/gnome/libgnomekbd")

def _close_desktop(mountpoint):
    _save_dconf(mountpoint, "/org/gnome/settings-daemon/plugins/power")
    _save_dconf(mountpoint, "/org/gnome/desktop/session")
    _save_gconf(mountpoint, "/desktop/gnome/keybindings")
    _save_gconf(mountpoint, "/apps/metacity")
    _save_dconf(mountpoint, "/org/gnome/settings-daemon/peripherals/mouse")
    _save_dconf(mountpoint, "/org/gnome/settings-daemon/peripherals/touchpad")
    _save_dconf(mountpoint, "/org/gnome/settings-daemon/peripherals/keyboard")
    _unlink_confdir(mountpoint, ".fonts")
    _unlink_conffile(mountpoint, ".gtk-bookmarks")
    _unlink_conffile(mountpoint, ".lockpasswd")
    _save_dconf(mountpoint, "/org/gnome/desktop/background")
    _save_dconf(mountpoint, "/org/gnome/nemo")
    _save_dconf(mountpoint, "/org/gnome/libgnomekbd")
    subprocess.call(["/usr/bin/dconf", "reset", "-f", "/org/gnome/desktop/background/"])

def _load_printers(mountpoint):
    if os.path.exists("%s/.cups/printers" % mountpoint):
        try:
            pconf = open("%s/.cups/printers" % mountpoint, 'r')
            printers = pickle.load(pconf)
            pconf.close()
            cupsc = cups.Connection()
            for printer in printers.keys():
                cupsc.addPrinter(name=printer, filename="%s/.cups/%s.ppd" % (mountpoint, printer),
                                 device=printers[printer]['device-uri'],
                                 info=printers[printer]['printer-info'],
                                 location=printers[printer]['printer-location'])
                cupsc.enablePrinter(printer)
                cupsc.acceptJobs(printer)
            defp = open("%s/.cups/default-printer" % mountpoint, 'r')
            cupsc.setDefault(defp.readline().strip())
            defp.close()
        except:
            pass

def _save_printers(mountpoint):
    try:
        if not os.path.exists("%s/.cups" % mountpoint):
            os.mkdir("%s/.cups" % mountpoint)
        pconf = open("%s/.cups/printers" % mountpoint, 'w')
        cupsc = cups.Connection()
        printers = cupsc.getPrinters()
        pickle.dump(printers, pconf)
        pconf.close()
        defp = open("%s/.cups/default-printer" % mountpoint, 'w')
        defp.write(cupsc.getDefault())
        defp.close()
        for printer in printers.keys():
            ppd = os.readlink(cupsc.getPPD(printer))
            shutil.copy(ppd, "%s/.cups/%s.ppd" % (mountpoint, printer))
    except:
        pass

def _open_vbox(mountpoint):
    if "vboxapi" not in sys.modules:
        return True
    _link_confdir(mountpoint, ".VirtualBox")
    _link_confdir(mountpoint, "VirtualBox VMs")
    _link_conffile(mountpoint, ".vbox-starter.conf")
    mgr = VirtualBoxManager(None, None)
    vbox = mgr.vbox
    vmx = mgr.getArray(vbox, 'machines')
    if len(vmx) > 0:
        if len(vmx) > 1:
            show_error(_("Multiple virtual machines were found on %s, don't know "
                         "which one to start. Please start it manually.") % mountpoint)
        else:
            vm = vmx[0].name.decode('utf-8', 'replace')
            if ask_user(_("Start Virtual Machine?"),
                        _("A virtual machine named \n%s\n was found. Do you want "
                          "to start it?") % vm):
                try:
                    subprocess.Popen(["/usr/bin/vbox-starter.sh", vm])
                except:
                    show_error(_("An error occured trying to start the virtual "
                                 "machine:\n%s") % sys.exc_info())

def _close_vbox(mountpoint):
    if "vboxapi" not in sys.modules:
        return True
    subprocess.call(["pkill", "VBoxSVC"])
    _unlink_confdir(mountpoint, ".VirtualBox")
    _unlink_confdir(mountpoint, "VirtualBox VMs")
    _unlink_conffile(mountpoint, ".vbox-starter.conf")

def _open_pulseaudio(mountpoint):
    if not os.path.exists("%s/.config/pulse" % mountpoint):
        fileutils.mkdir_p("%s/.config/pulse" % mountpoint)
    else:
        subprocess.call(["pulseaudio", "--kill"])
        fileutils.rm_rf(glob.glob("%s/.config/pulse/*runtime" % mountpoint))
        fileutils.cp(glob.glob("%s/.config/pulse/*" % mountpoint), "%s/.config/pulse" % os.environ["HOME"])
        subprocess.call(["pulseaudio", "--start"])

def _close_pulseaudio(mountpoint):
    subprocess.call(["pulseaudio", "--kill"])
    files = glob.glob("%s/.config/pulse/*" % os.environ["HOME"])
    ffiles = [k for k in files if not k.endswith("runtime")]
    fileutils.cp(ffiles, "%s/.config/pulse/" % mountpoint)
    subprocess.call(["pulseaudio", "--start"])

def _open_gimp(mountpoint):
    _link_confdir(mountpoint, ".gimp-2.8")
    if not os.path.exists("%s/.gimp-2.8/sessionrc" % mountpoint):
        if os.path.exists("/etc/skel/.gimp-2.8/sessionrc"):
            shutil.copy2("/etc/skel/.gimp-2.8/sessionrc", "%s/.gimp-2.8/" % mountpoint)

def _close_gimp(mountpoint):
    _unlink_confdir(mountpoint, ".gimp-2.8")

def _open_inkscape(mountpoint):
    _link_confdir(mountpoint, ".config/inkscape")

def _close_inkscape(mountpoint):
    _unlink_confdir(mountpoint, ".config/inkscape")

def _open_gthumb(mountpoint):
    _link_confdir(mountpoint, ".config/gthumb")
    _load_gconf(mountpoint, "/apps/gthumb")

def _close_gthumb(mountpoint):
    _unlink_confdir(mountpoint, ".config/gthumb")
    _save_gconf(mountpoint, "/apps/gthumb")

def _open_grsync(mountpoint):
    _link_confdir(mountpoint, ".grsync")

def _close_grsync(mountpoint):
    _unlink_confdir(mountpoint, ".grsync")

def _open_tracker(mountpoint):
    subprocess.call(["tracker-control", "-k", "all"])
    _link_confdir(mountpoint, ".cache/tracker")
    _link_confdir(mountpoint, ".config/tracker")
    _link_confdir(mountpoint, ".local/share/tracker")
    _load_dconf(mountpoint, "/org/freedesktop/tracker")
    subprocess.call(["tracker-control", "-s"])
    
def _close_tracker(mountpoint):
    subprocess.call(["tracker-control", "-k", "all"])
    _double_fork(["/usr/bin/gnome-shell", "--replace"])
    _unlink_confdir(mountpoint, ".cache/tracker")
    _unlink_confdir(mountpoint, ".config/tracker")
    _unlink_confdir(mountpoint, ".local/share/tracker")
    _save_dconf(mountpoint, "/org/freedesktop/tracker")
    subprocess.call(["tracker-control", "-s"])
    
def _open_icedove(mountpoint):
    if not os.path.exists(os.path.join(mountpoint, ".icedove")):
        if os.path.exists("/etc/skel/.icedove"):
            shutil.copytree("/etc/skel/.icedove", os.path.join(mountpoint, ".icedove"))
    _link_confdir(mountpoint, ".icedove")
    
def _close_icedove(mountpoint):
    _unlink_confdir(mountpoint, ".icedove")
    
def _open_backintime(mountpoint):
    _link_confdir(mountpoint, ".config/backintime")
    _link_confdir(mountpoint, ".local/share/backintime")
    try:
        subprocess.call(["/usr/bin/backintime", "check-config"])
    except:
        show_error(_("An error occured while checking the backup configuration."))
    
def _close_backintime(mountpoint):
    _unlink_confdir(mountpoint, ".config/backintime")
    _unlink_confdir(mountpoint, ".local/share/backintime")
    try:
        subprocess.call(["/usr/bin/backintime", "backup"])
    except:
        show_error(_("An error occured while trying to run a (last) snapshot."))

def _open_okular(mountpoint):
	_link_conffile(mountpoint, ".kde/share/config/okularrc")
	_link_conffile(mountpoint, ".kde/share/config/okularpartrc")    
	_link_confdir(mountpoint, ".kde/share/apps/okular")

def _close_okular(mountpoint):
	_unlink_conffile(mountpoint, ".kde/share/config/okularrc")
	_unlink_conffile(mountpoint, ".kde/share/config/okularpartrc")    
	_unlink_confdir(mountpoint, ".kde/share/apps/okular")
		
def _check_new_version(mountpoint):
    if os.path.exists("%s/.gnupg" % mountpoint) and not os.path.exists("%s/.icedove" % mountpoint):
        warnstring = _("You seem to be opening this extended container "\
            "for the first time with this version. Please be aware of "\
            "the following:\n"
            "* Evolution data cannot be migrated. Please open with " \
            "the old version instead, make a data backup within " \
            "evolution and restore it using this new version.\n" \
            "* The password manager database will be converted "\
            "and cannot be opened with older versions afterwards.\n"\
            "* Some seahorse settings cannot be migrated and need to"\
            "be re-done. This does not affect your keys or GnuPG "\
            "settings.\n"
            "* Beagle is not supported anymore, but its data will "\
            "remain on the container. You may manually delete the "\
            "folder '.beagle'.\n"
            "\n\n<b>Do you want to continue and open this extended "\
            "container?</b>")
        return ask_user(_("New Version"), warnstring)
    else:
        return True

def extvol_open(mountpoint, dmname):
    """ open an extended volume """
    global pyn
    syslog.syslog(syslog.LOG_DEBUG, "Opening volume at %s as extended volume" % \
                                    mountpoint.encode('ascii', 'replace'))
    # if the lock file says there's another one open, exit.
    if os.path.exists("%s/.mounted_as_extended_volume" \
        % os.environ["HOME"]):
        show_error(_("Either this is not an extended volume, or there is already "
                     "another extended volume mounted. There can only be one "
                     "extended volume mounted at a time."))
        return

    # Check free space
    s = os.statvfs(mountpoint.encode('utf-8'))
    df = (s.f_bavail * s.f_frsize)
    humanreadable = lambda s: [(s%1024**i and "%.1f"%(s/1024.0**i) or
                                str(s/1024**i))+x.strip() for i, x in
                               enumerate(' KMGTPEZY') if s < 1024**(i+1) or i == 8][0]
    if df < 10485760:
        if ask_user(_("Low free space"),
                    _("There are only %(freebytes)s free on %(volume)s. This may "
                      "cause problems when using it as an extended volume. You should "
                      "stop now, free some space and then try re-opening this as an "
                      "extended volume again.\n\nStop now?") % \
                      {"freebytes":humanreadable(df), "volume":mountpoint}):
            return

    # Check the version
    if not _check_new_version(mountpoint):
        return

    # open extended volume
    try:
        marker = open("%s/.mounted_as_extended_volume" % os.environ["HOME"], "w")
        marker.write("%s" % dmname)
        marker.close()
        pyn.update(_("Please wait..."),
                   _("Extended volume is being opened, please wait!"), "usbpendrive_unmount")
        pyn.show()

        _open_gnupg(mountpoint)
        _open_evolution(mountpoint)
        _open_hamster(mountpoint)
        _open_fpm(mountpoint)
        _open_libreoffice(mountpoint)
        _open_scribus(mountpoint)
        _open_gimp(mountpoint)
        _open_inkscape(mountpoint)
        _open_gthumb(mountpoint)
        _open_planner(mountpoint)
        _open_desktop(mountpoint)
        _load_printers(mountpoint)
        _open_vbox(mountpoint)
        _open_pulseaudio(mountpoint)
        _open_grsync(mountpoint)
        _open_kmymoney(mountpoint)
        _open_icedove(mountpoint)
        _open_tracker(mountpoint)
        _open_backintime(mountpoint)
        _open_okular(mountpoint)
        syslog.syslog(syslog.LOG_DEBUG, "... done.")

        # gconf-dumper will save above gconf dumps every 5 minutes, so you
        # have a fairly recent state after a crash or power loss
        syslog.syslog(syslog.LOG_DEBUG, "Starting the GConf dumper")
        subprocess.call(["gconf-dumper.py", "-t", mountpoint])

    except:
        show_error(variables=vars())
        return
    # Notify the user it's done
    pyn.update(_("Opening successful"), \
                        _("Extended volume opened successfully."),
               "usbpendrive_unmount")
    pyn.show()

def extvol_close(mountpoint):
    """ Close an extended Volume """
    global pyn
    mountpoint = mountpoint.rstrip('/')
    syslog.syslog(syslog.LOG_DEBUG, "Closing extended volume at %s" % \
                                    mountpoint.encode('ascii', 'replace'))
    if not os.path.ismount(mountpoint):
        syslog.syslog(syslog.LOG_DEBUG, "No extended volume found at %s" % \
                                         mountpoint.encode('ascii', 'replace'))
        return
    # Test open files
    syslog.syslog(syslog.LOG_DEBUG, "Looking for open files")
    openfiles = subprocess.Popen(["/usr/bin/sudo", "/usr/bin/lsof", "-w", "-F", "n"],
                                 stdout=subprocess.PIPE).communicate()[0]
    openfiles = re.findall("^n(%s/(?!.local/share/hamster-applet|.local/share/evolution|.config/tracker|.cache/tracker|.local/share/tracker|.VirtualBox/VBoxSVC.log).*)$" % mountpoint, openfiles, re.MULTILINE)
    if len(openfiles) > 0:
        message = (_("There are still open files on %s, listed below. Please close them first.\n\n") % mountpoint + '\n')
        message += '\n'.join(openfiles)
        show_error(message)
        return
    pyn.update(_("Please wait..."), _("Extended volume is being closed, please wait!"), "usbpendrive_unmount")
    pyn.show()

    #Stop the gconf dumper process, do a backup of the relevant gconf entries
    # kill evolution to make sure the volume can be dismounted later
    # restart gnome panel, clean up symlinks und copy back old folders if needed
    syslog.syslog(syslog.LOG_DEBUG, "Stopping the GConf dumper")
    subprocess.call(["/usr/bin/gconf-dumper.py", "-q"])
    subprocess.call(["evolution", "--force-shutdown"])
    _close_gnupg(mountpoint)
    _close_evolution(mountpoint)
    _close_hamster(mountpoint)
    _close_fpm(mountpoint)
    _close_libreoffice(mountpoint)
    _close_scribus(mountpoint)
    _close_gimp(mountpoint)
    _close_inkscape(mountpoint)
    _close_gthumb(mountpoint)
    _close_planner(mountpoint)
    _close_desktop(mountpoint)
    _save_printers(mountpoint)
    _close_vbox(mountpoint)
    _close_pulseaudio(mountpoint)
    _close_grsync(mountpoint)
    _close_kmymoney(mountpoint)
    _close_icedove(mountpoint)
    _close_tracker(mountpoint)

    subprocess.call(["/usr/bin/killall", "gconfd-2"])
    _close_backintime(mountpoint)
    _close_okular(mountpoint)
    #backupmp = _open_backup_container(mountpoint)
    #if backupmp:
    #    _do_backup(mountpoint, backupmp)
        # _backup_other_containers(dmname, backupmp)
    #    _close_backup_container(backupmp)
    syslog.syslog(syslog.LOG_DEBUG, "Syncing...")
    subprocess.call(["/bin/sync"])
    os.remove("%s/.mounted_as_extended_volume" % os.environ["HOME"])
    vm = Gio.VolumeMonitor.get()
    for mount in vm.get_mounts():
        if mount.get_root().get_path() == mountpoint:
            syslog.syslog(syslog.LOG_DEBUG, "Unmounting %s" % mountpoint.encode('ascii', 'replace'))
            try:
                mount.unmount(0, None, None, None)
            except:
                syslog.syslog(syslog.LOG_DEBUG, "Unmount failed!")
                show_error(_("Unmounting the volume at %s failed!") % mountpoint)
            else:
                pyn.update(_("Closing successful"), _("Extended volume closed successfully!"), "usbpendrive_unmount")
                pyn.show()

if __name__ == "__main__":
    print "This module cannot be called directly"
