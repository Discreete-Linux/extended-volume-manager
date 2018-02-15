#!/usr/bin/python3
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
try:
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Notify', '0.7')
    from gi.repository import Gtk, Notify, GLib, Gio
except:
    pass

try:
    from vboxapi import VirtualBoxManager
except:
    pass

gettext.install("extended-volume-manager")
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

def _chmod_R(mode, path):
    """ Apply the given permissions recursively to the given path. The
        "chmod" function documentation describes the mode argument.
    """
    if not os.path.exists(path):
        raise OSError("no such file or directory: '%s'" % path)
    os.chmod(path, mode)
    if os.path.isdir(path):
        child_paths = (os.path.join(path, c) for c in os.listdir(path))
        for child_path in child_paths:
            _chmod_R(mode, child_path)

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
    p = multiprocessing.Process(target=subprocess.run, args=(args,))
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
        message = _("A system error occured. " \
                    "The error was\n\n%(error)s\n\nLocal variables:\n%(vars)s") \
                    % {"error":traceback.format_exc(), "vars":str(variables)}
    else:
        syslog.syslog(message)
    dlg = Gtk.MessageDialog(type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK)
    dlg.format_secondary_text(message)
    dlg.run()
    dlg.destroy()
    while Gtk.events_pending():
        Gtk.main_iteration()
    return

def ask_user(title, message):
    """ Ask user a Yes/No question with message """
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
    """ Make everything under path read/writable for the current user """
    try:
        syslog.syslog(syslog.LOG_DEBUG, "Setting permissions on %s" % path)
        subprocess.run(["/usr/bin/sudo", "/bin/chown", "-R",
                         "%s:%s" % (str(os.getuid()), str(os.getgid())), path])
        subprocess.run(["/usr/bin/sudo", "/bin/chmod", "-R", "a+rwX", path])
    except:
        show_error(_("Could not set permissions and/or ownership on %s") % path)

def _link_confdir(mountpoint, confdir):
    """ Create a symlink for a directory from /home/$USER/confdir to
    mountpoint/confdir """
    try:
        syslog.syslog(syslog.LOG_DEBUG, "Configuration directory %s" % confdir)
        if not os.path.exists(os.path.join(mountpoint, confdir)):
            os.makedirs(os.path.join(mountpoint, confdir))
        if not os.path.exists(os.path.join(os.environ["HOME"], os.path.dirname(confdir))):
            os.makedirs(os.path.join(os.environ["HOME"], os.path.dirname(confdir)))
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
    """ Remove a symlink to a configuration directory from /home/$USER """
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
    """ Create a symlink for a file from /home/$USER/conffile to
    mountpoint/conffile """
    destfile = os.path.basename(conffile)
    if not destfile.startswith('.'):
        destfile = '.' + destfile
    try:
        syslog.syslog(syslog.LOG_DEBUG, "Configuration file %s" % conffile)
        if not os.path.exists(os.path.join(mountpoint, destfile)):
            os.mknod(os.path.join(mountpoint, destfile))
        if not os.path.exists(os.path.join(os.environ["HOME"], os.path.dirname(conffile))):
            os.makedirs(os.path.join(os.environ["HOME"], os.path.dirname(conffile)))
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
    """ Remove a symlink to a configuration file from /home/$USER """
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
            subprocess.run(["/usr/bin/gconftool-2", "--load",
                             "%s/.%s-backup.xml.dump" % (mountpoint, gconfkey.rsplit('/', 1)[1])])
    except:
        show_error(variables=vars())
        return False

def _save_gconf(mountpoint, gconfkey):
    try:
        dumpfile = open("%s/.%s-backup.xml.dump" % (mountpoint, gconfkey.rsplit('/', 1)[1]), 'w')
        syslog.syslog(syslog.LOG_DEBUG, "GConf key %s" % gconfkey)
        subprocess.run(["/usr/bin/gconftool-2", "--dump", "%s" % gconfkey], stdout=dumpfile)
        dumpfile.close()
    except:
        show_error(variables=vars())
        return False

def _load_dconf(mountpoint, dconfkey):
    dconfkey = dconfkey.rstrip('/')
    try:
        if os.path.exists("%s/.%s-backup.txt.dump" % (mountpoint, dconfkey.rsplit('/', 1)[1])):
            syslog.syslog(syslog.LOG_DEBUG, "DConf key %s" % dconfkey)
            subprocess.run(["/usr/bin/dconf", "load", "%s/" % dconfkey],
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
        subprocess.run(["/usr/bin/dconf", "dump", "%s/" % dconfkey], stdout=dumpfile)
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
        if os.path.exists(os.path.join(mountpoint, ".gnupg")):
            syslog.syslog(syslog.LOG_DEBUG, "Setting permissions on .gnupg")
            _chmod_R(0o0700, os.path.join(mountpoint, ".gnupg"))
        if not os.path.exists(os.path.join(mountpoint, ".gnupg", "gnupg-scripts.conf")):
            syslog.syslog(syslog.LOG_DEBUG, "Creating gnupg-scripts default configuration")
            subprocess.run(["/usr/bin/gpg-config", "--default"])
        if not os.path.exists(os.path.join(mountpoint, ".gnupg", "gpg-agent.conf")):
            syslog.syslog(syslog.LOG_DEBUG, "Copying default gpg-agent.conf")
            shutil.copy("/etc/skel/.gnupg/gpg-agent.conf", os.path.join(mountpoint, ".gnupg"))
    except:
        show_error(variables=vars())
        return False

def _close_gnupg(mountpoint):
    _save_dconf(mountpoint, "/apps/seahorse")
    _unlink_confdir(mountpoint, ".gnupg")
    try:
        syslog.syslog(syslog.LOG_DEBUG, "Reloading the gpg-agent")
        subprocess.run(["/usr/bin/pkill", "-HUP", "gpg-agent"])
    except:
        show_error(variables=vars())
        return False

def _really_kill_evolution():
    evoprocs = subprocess.run(["find", "/usr/lib/evolution", "-type", "f", "-and",
                                 "-executable", "-exec", "basename", "{}", ";"],
                                stdout=subprocess.PIPE, 
                                universal_newlines=True).stdout
    evoprocs = evoprocs.replace('\n', ',') + 'evolution'
    evopids = subprocess.run(["ps", "-C", evoprocs, "-o", "pid", "--no-headers"],
                               stdout=subprocess.PIPE,
                               universal_newlines=True).stdout
    if len(evopids) == 0:
        return True
    evopids = evopids.strip().split('\n')
    for pid in evopids:
        subprocess.run(["kill", pid])
        subprocess.run(["kill", "-9", pid])
    evopids = subprocess.run(["ps", "-C", evoprocs, "-o", "pid", "--no-headers"],
                               stdout=subprocess.PIPE,
                               universal_newlines=True).stdout
    if len(evopids) > 0:
        return False
    else:
        return True

def _open_evolution(mountpoint):
    syslog.syslog(syslog.LOG_DEBUG, "Shutting down evolution")
    subprocess.run(["/usr/bin/evolution", "--force-shutdown"],
                    stdout=open(os.devnull, 'w'), stderr=subprocess.STDOUT)
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
    subprocess.run(["/usr/bin/evolution", "--force-shutdown"],
                    stdout=open(os.devnull, 'w'), stderr=subprocess.STDOUT)
    _really_kill_evolution()
    _save_gconf(mountpoint, "/apps/evolution")
    _unlink_confdir(mountpoint, ".local/share/evolution")
    _unlink_confdir(mountpoint, ".config/evolution")
    _unlink_confdir(mountpoint, ".cache/evolution")

def _open_hamster(mountpoint):
    syslog.syslog(syslog.LOG_DEBUG, "Spawning the mighty hamster...")
    proclist = "hamster-service"
    pids = subprocess.run(["/bin/ps", "--no-headers", "-o", "pid", "-C", proclist],
                          stdout=subprocess.PIPE, universal_newlines=True).stdout
    for pid in pids.split():
        try:
            subprocess.run(["kill", pid])
            subprocess.run(["kill", "-9", pid])
        except:
            pass
    _migrate_confdir(mountpoint, ".gnome2/hamster-applet", ".local/share/hamster-applet")
    _link_confdir(mountpoint, ".local/share/hamster-applet")
    _load_gconf(mountpoint, "/apps/hamster-applet")
    subprocess.Popen(["/usr/lib/hamster-applet/hamster-service"])
    extlist = subprocess.run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
                             stdout=subprocess.PIPE, 
                             universal_newlines=True).stdout.strip('[]\n').split(', ')
    if "'hamster@projecthamster.wordpress.com'" not in extlist:
        extlist.append("'hamster@projecthamster.wordpress.com'")
        subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions",
                         "[" + ', '.join(extlist) + "]"])

def _close_hamster(mountpoint):
    syslog.syslog(syslog.LOG_DEBUG, "Stopping hamster applet")
    _save_gconf(mountpoint, "/apps/hamster-applet")
    _unlink_confdir(mountpoint, ".local/share/hamster-applet")
    proclist = "hamster-service"
    pids = subprocess.run(["/bin/ps", "--no-headers", "-o", "pid", "-C", proclist],
                          stdout=subprocess.PIPE, universal_newlines=True).stdout
    for pid in pids.split():
        try:
            subprocess.run(["kill", pid])
            subprocess.run(["kill", "-9", pid])
        except:
            pass
    extlist = subprocess.run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
                               stdout=subprocess.PIPE,
                               universal_newlines=True).stdout.strip('[]\n').split(', ')
    if "'hamster@projecthamster.wordpress.com'" in extlist:
        extlist = [x for x in extlist if x != "'hamster@projecthamster.wordpress.com'"]
        subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions",
                         "[" + ', '.join(extlist) + "]"])

def _open_keepass(mountpoint):
    _link_confdir(mountpoint, ".config/KeePass")

def _close_keepass(mountpoint):
    _unlink_confdir(mountpoint, ".config/KeePass")

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
    _load_dconf(mountpoint, "/org/gnome/desktop/peripherals")
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
    _save_dconf(mountpoint, "/org/gnome/desktop/peripherals")
    _unlink_confdir(mountpoint, ".local/share/fonts")
    _unlink_conffile(mountpoint, ".gtk-bookmarks")
    _unlink_conffile(mountpoint, ".lockpasswd")
    _save_dconf(mountpoint, "/org/gnome/desktop/background")
    _save_dconf(mountpoint, "/org/gnome/nemo")
    _save_dconf(mountpoint, "/org/gnome/libgnomekbd")
    subprocess.run(["/usr/bin/dconf", "reset", "-f", "/org/gnome/desktop/background/"])

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
            vm = vmx[0].name
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
    subprocess.run(["pkill", "VBoxSVC"])
    _unlink_confdir(mountpoint, ".VirtualBox")
    _unlink_confdir(mountpoint, "VirtualBox VMs")
    _unlink_conffile(mountpoint, ".vbox-starter.conf")

def _open_pulseaudio(mountpoint):
    if not os.path.exists("%s/.config/pulse" % mountpoint):
        os.makedirs("%s/.config/pulse" % mountpoint)
    else:
        subprocess.run(["pulseaudio", "--kill"])
        for f in glob.glob("%s/.config/pulse/*runtime" % mountpoint):
            try:
                os.remove(f)
            except:
                pass
        for f in glob.glob("%s/.config/pulse/*" % mountpoint):
            shutil.copy2(f, "%s/.config/pulse" % os.environ["HOME"])
        subprocess.run(["pulseaudio", "--start"])

def _close_pulseaudio(mountpoint):
    subprocess.run(["pulseaudio", "--kill"])
    files = glob.glob("%s/.config/pulse/*" % os.environ["HOME"])
    ffiles = [k for k in files if not k.endswith("runtime")]
    for f in ffiles:
        shutil.copy2(f, "%s/.config/pulse/" % mountpoint)
    subprocess.run(["pulseaudio", "--start"])

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
    subprocess.run(["tracker", "daemon", "-k", "all"], stdout=open(os.devnull, 'w'))
    _link_confdir(mountpoint, ".cache/tracker")
    _link_confdir(mountpoint, ".config/tracker")
    _link_confdir(mountpoint, ".local/share/tracker")
    _load_dconf(mountpoint, "/org/freedesktop/tracker")
    p = subprocess.run(["gsettings", "get", "org.freedesktop.Tracker.Miner.Files",
                        "index-recursive-directories"],
                       stdout=subprocess.PIPE, universal_newlines=True)
    locs = p.stdout.strip('[]\n').split(', ')
    mp = "'%s'" % mountpoint
    if not mp in locs:
        locs.append(mp)
        subprocess.run(["gsettings", "set", "org.freedesktop.Tracker.Miner.Files",
                        "index-recursive-directories", "[%s]" % ', '.join(locs)])
    subprocess.run(["tracker", "daemon", "-s"], stdout=open(os.devnull, 'w'))

def _close_tracker(mountpoint):
    subprocess.run(["tracker", "daemon", "-k", "all"], stdout=open(os.devnull, 'w'))
    #_double_fork(["/usr/bin/gnome-shell", "--replace"])
    _unlink_confdir(mountpoint, ".cache/tracker")
    _unlink_confdir(mountpoint, ".config/tracker")
    _unlink_confdir(mountpoint, ".local/share/tracker")
    _save_dconf(mountpoint, "/org/freedesktop/tracker")
    subprocess.run(["tracker", "daemon", "-s"], stdout=open(os.devnull, 'w'))

def _open_thunderbird(mountpoint):
    if not os.path.exists(os.path.join(mountpoint, ".thunderbird")):
        if os.path.exists("/etc/skel/.thunderbird"):
            shutil.copytree("/etc/skel/.thunderbird", 
                            os.path.join(mountpoint, ".thunderbird"))
    _link_confdir(mountpoint, ".thunderbird")

def _close_thunderbird(mountpoint):
    _unlink_confdir(mountpoint, ".thunderbird")

def _open_backintime(mountpoint):
    _link_confdir(mountpoint, ".config/backintime")
    _link_confdir(mountpoint, ".local/share/backintime")
    try:
        if not os.path.exists(os.path.join(mountpoint, ".config/backintime", "config")):
            if ask_user(_("Setup backup"),
                        _("You have not yet configured a backup for this "
                          "volume yet. I can create a default configuration "
                          "which you can change later using the BackInTime "
                          "application.\n"
                          "You will need to create a backup volume using "
                          "the volume wizard, if you have not already done "
                          "so.\n"
                          "Do you want to create a backup configuration now?")):
                shutil.copyfile("/usr/share/extended-volume-manager/backintime-config.tmpl",
                                 os.path.join(mountpoint, ".config/backintime/config"))
                with open(os.path.join(mountpoint, ".config/backintime/config"), 'a') as conf:
                    conf.writelines("profile1.snapshots.include.1.value=%s" % mountpoint)
    except:
        show_error(_("An error occured while trying to create a default configuration."))
    backupdir = os.path.join("/media", os.environ['USER'], "backup")
    try:
        if not os.path.isdir(backupdir):
            subprocess.run(["sudo", "mkdir", "-m", "777", backupdir])
        subprocess.run(["/usr/bin/backintime", "--quiet", "check-config"], check=True)
    except:
        show_error(_("An error occured while checking the backup configuration."))
    if os.path.isdir(backupdir):
        subprocess.run(["sudo", "rmdir", backupdir])

def _close_backintime(mountpoint):
    backupdir = os.path.join("/media", os.environ['USER'], "backup")
    if os.path.isdir(backupdir):
        try:
            subprocess.run(["/usr/bin/backintime", "backup"], check=True)
        except:
            show_error(_("An error occured while trying to run a (last) snapshot."))
    _unlink_confdir(mountpoint, ".config/backintime")
    _unlink_confdir(mountpoint, ".local/share/backintime")

def _open_okular(mountpoint):
    _link_conffile(mountpoint, ".kde/share/config/okularrc")
    _link_conffile(mountpoint, ".kde/share/config/okularpartrc")
    _link_confdir(mountpoint, ".kde/share/apps/okular")

def _close_okular(mountpoint):
    _unlink_conffile(mountpoint, ".kde/share/config/okularrc")
    _unlink_conffile(mountpoint, ".kde/share/config/okularpartrc")
    _unlink_confdir(mountpoint, ".kde/share/apps/okular")

def _check_new_version(mountpoint):
    if os.path.exists("%s/.gnupg" % mountpoint) and not os.path.exists("%s/.thunderbird" % mountpoint):
        warnstring = _("You seem to be opening an extended container "\
            "previously created with Ubuntu Privacy Remix. "\
            "Please be aware of the following:\n"
            "* Evolution data cannot be migrated. Please open with " \
            "the old version instead, make a data backup within " \
            "evolution and restore it using this new version.\n" \
            "* The password manager FPM is not supported anymore.\n" \
            "We now use KeePass 2 instead. FPM data will remain on the "\
            "container; please open it with UPR and export your passwords, " \
            "then import them into KeePass with Discreete Linux.\n" \
            "* <b>The keyring format of GnuPG has changed! Your existing "
            "keys will be converted, and the old keyrings will remain in "
            "place. This means you can use the keys you have right now "
            "both with UPR and Discreete Linux. But any newly imported "
            "or created keys will only be usable on the system they "
            "were imported/created on. Please read the manual for "
            "further details!</b>"
            "\n\n<b>Do you want to continue and open this extended "\
            "container?</b>")
        return ask_user(_("New Version"), warnstring)
    else:
        return True

def extvol_open(mountpoint):
    """ open an extended volume """
    global pyn
    syslog.syslog(syslog.LOG_DEBUG, "Opening volume at %s as extended volume" % \
                                    mountpoint)
    # if the lock file says there's another one open, exit.
    if os.path.exists("%s/.mounted_as_extended_volume" \
        % os.environ["HOME"]):
        show_error(_("Either this is not an extended volume, or there is already "
                     "another extended volume mounted. There can only be one "
                     "extended volume mounted at a time."))
        return

    # Check free space
    s = os.statvfs(mountpoint)
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
        with open("%s/.mounted_as_extended_volume" % os.environ["HOME"], "w") as marker:
            marker.write("%s" % mountpoint)
        pyn.update(_("Please wait..."),
                   _("Extended volume is being opened, please wait!"), "usbpendrive_unmount")
        pyn.show()

        _open_gnupg(mountpoint)
        _open_evolution(mountpoint)
        _open_hamster(mountpoint)
        _open_keepass(mountpoint)
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
        _open_thunderbird(mountpoint)
        _open_tracker(mountpoint)
        _open_backintime(mountpoint)
        _open_okular(mountpoint)
        syslog.syslog(syslog.LOG_DEBUG, "... done.")

        # gconf-dumper will save above gconf dumps every 5 minutes, so you
        # have a fairly recent state after a crash or power loss
        syslog.syslog(syslog.LOG_DEBUG, "Starting the GConf dumper")
        subprocess.run(["gconf-dumper.py", "-t", mountpoint])

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
    with open("%s/.mounted_as_extended_volume" % os.environ["HOME"], "r") as marker:
        extvolmount = marker.readline().strip()
    if not os.path.ismount(mountpoint) or (mountpoint != extvolmount):
        syslog.syslog(syslog.LOG_DEBUG, "No extended volume found at %s" % \
                                         mountpoint.encode('ascii', 'replace'))
        return
    syslog.syslog(syslog.LOG_DEBUG, "Closing extended volume at %s" % \
                                    mountpoint.encode('ascii', 'replace'))
    # Test open files
    syslog.syslog(syslog.LOG_DEBUG, "Looking for open files")
    openfiles = subprocess.run(["/usr/bin/sudo", "/usr/bin/lsof", "-w", "-F", "n"],
                                 stdout=subprocess.PIPE,
                                 universal_newlines=True).stdout
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
    subprocess.run(["/usr/bin/gconf-dumper.py", "-q"])
    subprocess.run(["evolution", "--force-shutdown"])
    _close_gnupg(mountpoint)
    _close_evolution(mountpoint)
    _close_hamster(mountpoint)
    _close_keepass(mountpoint)
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
    _close_thunderbird(mountpoint)
    _close_tracker(mountpoint)

    subprocess.run(["/usr/bin/killall", "gconfd-2"])
    _close_backintime(mountpoint)
    _close_okular(mountpoint)
    syslog.syslog(syslog.LOG_DEBUG, "Syncing...")
    subprocess.run(["/bin/sync"])
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
    print("This module cannot be called directly")
