#!/usr/bin/env python
# Extended Volume Manager Plugin for Nemo
#
# Part of "extended-volume-manager" Package
#
# Copyright 2010-2016 Discreete Linux Team <info@discreete-linux.org>
#
# Portions of the code taken from TortoiseHG nemo extension,
# Copyright 2007 Steve Borho
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.
#
# Encoding: UTF-8
""" A nemo extension which allows closing extended Volumes """
import gettext
import os
import subprocess
import urllib
from multiprocessing import Process
from gi.repository import GObject, Nemo

class ExtvolManagerExtension(GObject.GObject, Nemo.MenuProvider, Nemo.InfoProvider):
    """ Allows closing extended Volumes """
    def __init__(self):
        """ Init the extionsion. """
        print "Initializing nemo-extvol-manager extension"

    def close_activate_cb(self, menu, myfile):
        """ Handle menu activation, i.e. actual closing """
        mountpoint = myfile.get_mount().get_root().get_path().decode('utf-8', 'replace')
        Process(target=subprocess.call, args=(("/usr/bin/extvol-close", mountpoint), )).start()
        return

    def is_valid_drive(self, myfile):
        """ Check if myfile is a valid drive for us """
        # Drive icon on desktop
        if (myfile.get_uri_scheme() == 'x-nemo-desktop') and \
            (myfile.get_mime_type() == 'application/x-nemo-link'):
            return True
        # Icon in computer:/// view
        elif myfile.get_uri_scheme() == 'computer':
            return True
        # Drive icon in the side panel
        elif (myfile.get_uri_scheme() == 'file') and \
            (os.path.ismount(urllib.unquote(myfile.get_uri()[7:]))):
            return True
        else:
            return False

    def get_file_items(self, window, files):
        """ Tell nemo whether and when to show the menu """
        if len(files) != 1:
            return
        myfile = files[0]
        isdrive = self.is_valid_drive(myfile)
        if not isdrive:
            return
        item = Nemo.MenuItem(name='Nemo::extvol_close',
                             label=gettext.dgettext('extended-volume-manager', 'Close extended volume'),
                             tip=gettext.dgettext('extended-volume-manager',
                                                  'Closes and Unmounts the selected extended Volume'))
        item.connect('activate', self.close_activate_cb, myfile)
        return item,
