��    1      �  C   ,      8  �   9  �   	  K   �  @   2  B   s  S   �  G   
  8   R  9   �  7   �     �     
     #     <     H  0   ^     �  (   �  !   �  0   �     	  �   :	     �	  $   �	  -   
  -   2
     `
  $   y
  W   �
  �   �
  ;   y     �  �   �  d   �     �  0        3  6   F     }     �  �   �  J   {  ^   �     %  
   9  #   D  �   h  �  G  �  �    �    �  W   �  L     O   S  T   �  Y   �  H   R  >   �  M   �     (     >     Y  
   s      ~  1   �     �  4   �  )     6   G     ~  �   �     Y  4   o  5   �  3   �       2   '  f   Z  �   �  O   Y     �    �  t   �     =  0   J     {  C   �     �     �  �   �  w   �   j   p!     �!  
   �!  -   �!  �   ("    	#     *   1              -            '      	   (       0   #      +                               !                
          )          $                    ,                 &                 /   "       .                   %              %(backupname)s is not an "extended volume" and can therefore not be used for a backup.
Please convert %(backupname)s to an "extended Volume" or create a new, ext3 formatted backup volume with name backup.tc. %(backupname)s looks like an encrypted backup container. Do you want to use it for a backup of your files in %(origname)s? If you answer with "OK", you will have to enter the password for %(backupname)s in the next step. A system error occured. The error was

%(error)s

Local variables:
%(vars)s A virtual machine named 
%s
 was found. Do you want to start it? An error occured during backup!
Could not create target directory. An error occured during backup!
Maybe there is not enough space at the destination. An error occured during backup. Error occured while executing gtkrsync! An error occured trying to start the virtual machine:
%s An error occured while checking the backup configuration. An error occured while trying to run a (last) snapshot. Backup done. Backup of %s successful. Backup other containers? Cleaning up Close extended volume Closes and Unmounts the selected extended Volume Closing successful Could not delete incomplete backup at %s Could not delete old backup at %s Could not set permissions and/or ownership on %s Do you want to da a backup? Either this is not an extended volume, or there is already another extended volume mounted. There can only be one extended volume mounted at a time. Extended volume Extended volume closed successfully! Extended volume is being closed, please wait! Extended volume is being opened, please wait! Extended volume listener Extended volume opened successfully. Failed to stop evolution, will skip loading evolution data from the extended container! It looks like you have a backup container/volume mounted at /media/backup. Do you want to use it for a backup of your files in %s? Listens for mounted volumes which could be extended volumes Low free space More than one possible backup container or device was found. Automatic backup cannot continue. Please make sure only one backup container or device is present.

I have found these containers and devices:
 Multiple virtual machines were found on %s, don't know which one to start. Please start it manually. New Version Old backups are being cleaned up, please wait... Opening successful Please wait until all data has been written to disk... Please wait... Start Virtual Machine? There are only %(freebytes)s free on %(volume)s. This may cause problems when using it as an extended volume. You should stop now, free some space and then try re-opening this as an extended volume again.

Stop now? There are still open files on %s, listed below. Please close them first.

 This appears to be an extended Volume. Do you want to make use of the settings stored therein? Too many arguments. Unmounting Unmounting the volume at %s failed! You can now backup your other open containers as well. Their contents will be stored within the same backup container, but in a separate directory. Do you want to do this now?

Hint: The backup container has %s free space. You seem to be opening this extended container for the first time with this version. Please be aware of the following:
* Evolution data cannot be migrated. Please open with the old version instead, make a data backup within evolution and restore it using this new version.
* The password manager database will be converted and cannot be opened with older versions afterwards.
* Some seahorse settings cannot be migrated and need tobe re-done. This does not affect your keys or GnuPG settings.
* Beagle is not supported anymore, but its data will remain on the container. You may manually delete the folder '.beagle'.


<b>Do you want to continue and open this extended container?</b> Project-Id-Version: extended-volume-manager 0.1
Report-Msgid-Bugs-To: info@discreete-linux.org
POT-Creation-Date: 2017-03-02 11:12+0100
PO-Revision-Date: 2017-03-02 11:16+0100
Last-Translator: Discreete Linux Team <info@discreete-linux.org>
Language-Team: LANGUAGE <de@li.org>
Language: de
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 8bit
X-Generator: Poedit 1.6.10
 %(backupname)s ist kein "erweiterter Container" und kann deshalb nicht für ein Backup verwendet werden.
Bitte konvertieren Sie %(backupname)s zu einem "erweiterten Truecrypt-Container" oder legen Sie einen neuen, ext3-formatierten Backup-Container mit dem Namen backup.tc an. %(backupname)s scheint ein verschlüsselter Backup-Container zu sein. Soll er für eine Sicherung der Daten im Container %(origname)s verwendet werden? Wenn Sie mit "OK" antworten, müssen Sie im nächsten Schritt das Passwort für den Container %(backupname)s eingeben Ein Systemfehler ist aufgetreten. Der Fehler war

%(error)s

Lokale Variablen:
%(vars)s Eine virtuelle Maschine namens
%s
wurde gefunden. Soll sie gestartet werden? Beim Backup ist ein Fehler aufgetreten!
Konnte Zielverzeichnis nicht erstellen. Beim Backup ist ein Fehler aufgetreten!
Eventuell ist am Ziel nicht genügend Platz. Beim Backup ist ein Fehler aufgetreten!
Ein Fehler trat auf beim Ausführen von gtkrsync! Ein Fehler trat auf beim Versuch, die virtuelle Maschine:
%s
zu starten. Ein Fehler trat auf bei der Prüfung der Backup-Einstellungen. Ein Fehler trat auf beim Versuch, einen (letzten) Schnappschuss zu erstellen. Backup abgeschlossen. Backup von %s erfolgreich. Andere Container sichern? Aufräumen Erweiterten Container schließen Schließt des ausgewählten erweiterten Container Schließen erfolgreich Konnte unvollständiges Backup auf %s nicht löschen Konnte altes Backup auf %s nicht löschen Konnte Rechte und/oder Eigentümer auf %s nicht setzen Wollen Sie ihre Daten sichern? Entweder ist dies kein erweiterter Container, oder es ist bereits ein anderer erweiterter Container eingehängt. Es kann immer nur ein erweiterter Container gleichzeitig eingehängt sein. Erweiterter Container Erweiterter Container wurde erfolgreich geschlossen. Erweiterter Container wird geschlossen, bitte warten! Erweiterter Container wird geöffnet, bitte warten! Extended volume listener Erweiterter Container wurde erfolgreich geöffnet. Konnte Evolution nicht anhalten, überspringe das Laden der Evolution-Daten vom erweiterten Container! Es scheint, als wäre bereits ein Backup-Container auf /media/backup geöffnet. Soll er für eine Sicherung der Daten im Container %s verwendet werden? Sucht nach eingehängten Datenträgern, die "erweiterte Volumes" sein könnten. Wenig freier Speicherplatz Es wurde mehr als ein möglicher Backup-Container oder -Gerät gefunden. Das automatische Backup kann nicht ausgeführt werden. Bitte stellen Sie sicher, dass nur ein Backup-Container oder -Gerät existiert.

Ich habe folgende Geräte und Container gefunden:
 Mehrere virtuelle Maschinen wurden auf %s gefunden, weiss nicht welche gestartet werden soll. Bitte manuell starten. Neue Version Alte Backups werden aufgeräumt, bitte warten... Öffnen erfolgreich Bitte warten, bis alle Daten auf Datenträger geschrieben wurden... Bitte warten... Virtuelle Maschine starten? Es sind nur noch %(freebytes)s frei auf %(volume)s. Das kann Probleme verursachen beim Verwenden als erweiterter Container. Sie sollten jetzt abbrechen, etwas Speicherplatz schaffen und den Container erneut als erweiterten öffnen.

Jetz abbrechen? Es sind noch Dateien auf %s geöffnet, die unten aufgelistet sind.Bitte diese zuerst schließen und erneut versuchen.

 Dies scheint ein erweiterter Container zu sein. Wollen Sie die darin gespeicherten Einstellungen benutzen? Zu viele Argumente. Aushängen Aushängen des Volumes auf %s fehlgeschlagen! Sie können jetzt auch andere geöffnete Container mit sichern. Ihr Inhalt wird im gleichen Backup-Container, aber in einem extra Ordner gespeichert. Wollen Sie das jetzt tun?

Hinweis: Der Backup-Container hat noch %s frei. Sie öffnen diesen erweiterten Container offenbar zum ersten Mal mit dieser Version. Bitte beachten Sie folgendes:
* Evolution-Daten können nicht übernommen werden. Bitte statt dessen mit der alten Version öffnen, in Evolution eine Datensicherung durchführen und diese in der neuen Version importieren.
* Die Passwort-Manager-Datenbank wird konvertiert und kann danach mit älteren Versionen u.U. nicht mehr geöffnet werden.
* Einige Einstellungen der Schlüsselverwaltung Seahorse können nicht übernommen werden. Dies betrifft nicht die Schlüssel oder GnuPG-Einstellungen.
* Beagle Volltextsuche wird nicht mehr unterstützt, aber die Daten verbleiben im Container. Sie können den Ordner ".beagle" manuell löschen.


<b>Wollen Sie fortfahren und diesen erweiterten Container öffnen?</b> 