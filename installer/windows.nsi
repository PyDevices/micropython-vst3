; Windows installer for the MPVST plug-in.
;
; Built from Linux by scripts/package-windows.sh through makensis, so the
; release path needs no Windows toolchain:
;
;   makensis -DMPVST_VERSION=x.y.z -DMPVST_STAGE=<dir> -DMPVST_OUTFILE=<exe> \
;            installer/windows.nsi
;
; MPVST_STAGE is a directory holding MPVST.vst3, README.md and LICENSE -
; the same staging tree the .zip is built from, so the archive and the
; installer cannot ship different bytes.

Unicode true
SetCompressor /SOLID lzma

!include "MUI2.nsh"
!include "FileFunc.nsh"

!ifndef MPVST_VERSION
  !error "MPVST_VERSION is required"
!endif
!ifndef MPVST_STAGE
  !error "MPVST_STAGE is required"
!endif
!ifndef MPVST_OUTFILE
  !error "MPVST_OUTFILE is required"
!endif

!define PRODUCT "MPVST"
!define PUBLISHER "PyDevices"
!define BUNDLE "MPVST.vst3"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\MPVST"

Name "${PRODUCT} ${MPVST_VERSION}"
OutFile "${MPVST_OUTFILE}"
BrandingText "${PUBLISHER}"

; Per-user by default, which is why there is no UAC prompt: the VST3
; directory below is the one a user owns. Someone who points the directory
; page at Program Files will be told by Windows that they cannot write there,
; which is a better failure than asking every user for elevation they do not
; need.
RequestExecutionLevel user

; INSTDIR is the VST3 SCAN DIRECTORY, not a folder of our own: the bundle
; goes in beside every other plug-in the host scans. Support files and the
; uninstaller go somewhere private instead, because dropping a README and an
; uninstaller into a shared plug-in folder is how that folder becomes a mess.
InstallDir "$LOCALAPPDATA\Programs\Common\VST3"
InstallDirRegKey HKCU "Software\${PUBLISHER}\MPVST" "VST3Directory"

!define SUPPORTDIR "$LOCALAPPDATA\Programs\${PRODUCT}"

VIProductVersion "${MPVST_VERSION}.0"
VIAddVersionKey "ProductName" "${PRODUCT}"
VIAddVersionKey "CompanyName" "${PUBLISHER}"
VIAddVersionKey "FileDescription" "${PRODUCT} plug-in installer"
VIAddVersionKey "FileVersion" "${MPVST_VERSION}"
VIAddVersionKey "ProductVersion" "${MPVST_VERSION}"
VIAddVersionKey "LegalCopyright" "${PUBLISHER}"

!define MUI_ABORTWARNING
!define MUI_LICENSEPAGE_TEXT_BOTTOM "If you accept the terms of the \
agreement, click I Agree to continue."
!define MUI_WELCOMEPAGE_TITLE "${PRODUCT} ${MPVST_VERSION}"
!define MUI_WELCOMEPAGE_TEXT "This installs the ${PRODUCT} plug-in for the \
current user.$\r$\n$\r$\nClose your DAW before continuing."
!define MUI_DIRECTORYPAGE_TEXT_TOP "The ${BUNDLE} bundle will be installed \
into the folder below. This is the per-user VST3 folder every current host \
scans; change it only if yours is configured to scan somewhere else."
!define MUI_DIRECTORYPAGE_TEXT_DESTINATION "VST3 folder"
!define MUI_FINISHPAGE_TEXT "${PRODUCT} is installed.$\r$\n$\r$\nStart your \
DAW and rescan plug-ins."
!define MUI_FINISHPAGE_LINK "Read the README"
!define MUI_FINISHPAGE_LINK_LOCATION "${SUPPORTDIR}\README.md"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${MPVST_STAGE}\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "Plug-in" SecPlugin
    SectionIn RO

    ; A partial bundle is worse than no bundle - a host that scans one will
    ; report a broken plug-in rather than an absent one - so an upgrade
    ; removes the old tree before writing the new one.
    RMDir /r "$INSTDIR\${BUNDLE}"
    SetOutPath "$INSTDIR\${BUNDLE}"
    File /r "${MPVST_STAGE}\${BUNDLE}\*.*"

    ; Clicking Finish should leave it finished. moduleinfo.json is what the
    ; host reads to enumerate the plug-ins, and it ships generated - but the
    ; scan costs a moment and makes the installed tree self-consistent no
    ; matter what was staged. This is the same command the README gives for
    ; rescanning after adding a script of your own, run from the same folder.
    SetOutPath "$INSTDIR\${BUNDLE}\Contents\x86_64-win"
    nsExec::ExecToLog '"$INSTDIR\${BUNDLE}\Contents\x86_64-win\mpvst-engine.exe" mpvst_scan_plugins.py'
    Pop $0
    ; catalog.json for tools; nothing the plug-in loads needs it, so its
    ; result is not even checked.
    nsExec::ExecToLog '"$INSTDIR\${BUNDLE}\Contents\x86_64-win\mpvst-engine.exe" mpvst_catalog.py'
    Pop $1
    ; Not fatal: a failed rescan leaves the moduleinfo.json that shipped in the
    ; bundle, which is valid. Said out loud rather than swallowed.
    StrCmp $0 "0" +2 0
    DetailPrint "Plug-in scan returned $0; the list that shipped in the bundle is unchanged."

    SetOutPath "${SUPPORTDIR}"
    File "${MPVST_STAGE}\README.md"
    File "${MPVST_STAGE}\LICENSE"

    WriteRegStr HKCU "Software\${PUBLISHER}\MPVST" "VST3Directory" "$INSTDIR"
    WriteRegStr HKCU "Software\${PUBLISHER}\MPVST" "Version" "${MPVST_VERSION}"

    WriteUninstaller "${SUPPORTDIR}\Uninstall.exe"

    WriteRegStr HKCU "${UNINSTKEY}" "DisplayName" "${PRODUCT}"
    WriteRegStr HKCU "${UNINSTKEY}" "DisplayVersion" "${MPVST_VERSION}"
    WriteRegStr HKCU "${UNINSTKEY}" "Publisher" "${PUBLISHER}"
    WriteRegStr HKCU "${UNINSTKEY}" "UninstallString" "$\"${SUPPORTDIR}\Uninstall.exe$\""
    WriteRegStr HKCU "${UNINSTKEY}" "QuietUninstallString" "$\"${SUPPORTDIR}\Uninstall.exe$\" /S"
    WriteRegStr HKCU "${UNINSTKEY}" "InstallLocation" "${SUPPORTDIR}"
    WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
    WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1

    ; Add/Remove Programs shows a size, and an installer that leaves it at
    ; zero looks like it failed halfway.
    ${GetSize} "$INSTDIR\${BUNDLE}" "/S=0K" $0 $1 $2
    IntOp $0 $0 + 1024
    WriteRegDWORD HKCU "${UNINSTKEY}" "EstimatedSize" $0
SectionEnd

Section "Uninstall"
    ; The bundle is not under $INSTDIR here - $INSTDIR is the support folder
    ; the uninstaller lives in - so read back where it actually went.
    ReadRegStr $0 HKCU "Software\${PUBLISHER}\MPVST" "VST3Directory"
    StrCmp $0 "" +2 0
    RMDir /r "$0\${BUNDLE}"

    Delete "$INSTDIR\README.md"
    Delete "$INSTDIR\LICENSE"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir "$INSTDIR"

    DeleteRegKey HKCU "${UNINSTKEY}"
    DeleteRegKey HKCU "Software\${PUBLISHER}\MPVST"
SectionEnd
