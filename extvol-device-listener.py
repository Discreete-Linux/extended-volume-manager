#!/usr/bin/python
# Encoding: UTF-8

import os.path
from gi.repository import GObject, Gio
from dbus.mainloop.glib import DBusGMainLoop
import extvolmanager

class ExtvolDeviceListener(object):
    def mount_added(self, obj, data):
        mountpoint = data.get_root().get_path().rstrip('/')
        device = data.get_volume().get_identifier("unix-device")
        if device.startswith("/dev/dm-") and os.path.exists(os.path.join(mountpoint, ".extended_volume")):
            if extvolmanager.ask_user(_("Extended volume"),
                                      _("This appears to be an extended TrueCrypt Volume. "
                                        "Do you want to make use of the settings "
                                        "stored therein?")):
                extvolmanager.ext_tc_open(mountpoint, device)

    def __init__(self):
        self.vm = Gio.VolumeMonitor.get()
        for mount in self.vm.get_mounts():
            self.mount_added(None, mount)
        self.vm.connect("mount-added", self.mount_added)

if __name__ == "__main__":
    DBusGMainLoop(set_as_default=True)
    loop = GObject.MainLoop()
    ExtvolDeviceListener()
    loop.run()
