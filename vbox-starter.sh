#!/bin/bash

test -x /usr/bin/VBoxManage || exit 1

# Starte die als Parameter angegebene VM mit Anpassungen an die jeweils
# erkannte Hardware:
# * CPU-Kerne: (vorhandene Kerne) - (fuer den Host reservierte Kerne)
#   Standard fuer den Host reserviert = 1, kann in ~/.vbox-starter.conf
#   angepasst werden (s.u.). Logische Kerne durch HyperThreading
#   zaehlen nicht, AMD-Bulldozer-Module zaehlen.
#   Wenn in der VM der IOAPIC deaktiviert ist, kann immer nur 1 CPU
#   verwendet werden.
# * Speicher: (vorhandener RAM) - (fuer den Host reservierter RAM)
#   Standard fuer den Host reserviert = 1024, kann in ~/.vbox-starter.conf
#   angepasst werden (s.u.). Auf 32-Bit-Hosts wird der Speicher auf
#   3584 MB limitiert, da der gesamte VirtualBox-Prozess nicht mehr als
#   4096 MB inkl. "Eigenbedarf" nutzen kann (auch nicht mit PAE-Kernel).
#   Fuer 32-Bit-Gaeste wird der Speicher auf 4096 MB limitiert.
# * (de)aktivierung von VT-x/Nested Paging und PAE entsprechend den 
#   Moeglichkeiten der Hardware.

# Standardwerte  
PAE=off
VTX=off
VPID=off
VTXEXC=off
NPAGING=off
RESERVED_MEM=1024
RESERVED_CPU=1

# ggf. ueberschreiben der Standardwerte durch ~/.vbox-starter.conf
test -r ~/.vbox-starter.conf && . ~/.vbox-starter.conf

# Anpassung der Werte entsprechend der Hardware
arr=("$1")
ARCHITECTURE=$(uname -i)
IOAPIC=$( VBoxManage showvminfo "${arr[@]}" | grep IOAPIC | cut -d ':' -f 2 | sed 's/ //g')
GUESTARCH=$( VBoxManage showvminfo "${arr[@]}" | grep "Guest OS" | egrep -o "\((32|64)-bit\)")
egrep -q "vmx" /proc/cpuinfo && VTX=on
egrep -q "vmx" /proc/cpuinfo && VPID=on
egrep -q "svm" /proc/cpuinfo && VTX=on
egrep -q "pae" /proc/cpuinfo && PAE=on
egrep -q "AuthenticAMD" /proc/cpuinfo && AMDCPU=1

# CPU-Einstellung
if [ "$IOAPIC" = "off" ]; then
    NUMCPUS=1
else
    NUMCPUS=$(grep -m 1 "cpu cores" /proc/cpuinfo | cut -d ':' -f 2 | sed 's/ //g')
    if [ $AMDCPU -eq 1 ]; then
	NUMCPUS=$(grep -c "core id" /proc/cpuinfo)
    fi
    if [ -z $NUMCPUS ]; then
        NUMCPUS=$(egrep -c processor /proc/cpuinfo)
    fi
    if [ $NUMCPUS -gt 1 ]; then
        let NUMCPUS-=${RESERVED_CPU}
    fi
    if [ $NUMCPUS -lt 1 ]; then
	NUMCPUS = 1
    fi
fi

if [ "$VTX" == "off" ]; then
    NUMCPUS=1
else
    NPAGING=on
fi

# Speicher-Einstellung
MEMORY=$(/bin/grep MemTotal /proc/meminfo | /usr/bin/awk "{ printf \"%d\n\", \$2/1024-${RESERVED_MEM}; }")

if [ $MEMORY -lt 512 ]; then
        zenity --error --text "Nicht genug Speicher zum starten der virtuellen Maschine!"
        exit 1
fi

if [ $MEMORY -gt 3584 -a "$ARCHITECTURE" != "x86_64" ]; then
   MEMORY=3584
fi

if [ $MEMORY -gt 4096 -a "$GUESTARCH" = "(32-bit)" ]; then
   MEMORY=4096
fi

# ueberfluessige Warnmeldungen unterdruecken
VBoxManage setextradata global "GUI/SuppressMessages" "remindAboutAutoCapture,remindAboutMouseIntegrationOn,remindAboutGoingSeamless,remindAboutInputCapture,remindAboutGoingFullscreen,remindAboutMouseIntegrationOff,confirmGoingSeamless,confirmInputCapture,remindAboutPausedVMInput,confirmGoingFullscreen,remindAboutWrongColorDepth,remindAboutMouseIntegration"

# Anpassungen durchfuehren
VBoxManage modifyvm "${arr[@]}" --memory $MEMORY --pae $PAE --hwvirtex $VTX \
--nestedpaging $NPAGING --vtxvpid $VPID --cpus $NUMCPUS --paravirtprovider default \
--nic1 none

# VM starten
VirtualBox --startvm "${arr[@]}" --fullscreen
