; Lucid NSIS installer script.
; Expects PyInstaller output at ..\dist\lucid\ and an icon at ..\assets\icon.ico.
; Build: makensis /DVERSION=0.1.0 lucid.nsi

!ifndef VERSION
    !define VERSION "0.1.0"
!endif

!define APPNAME "Lucid"
!define COMPANY "Lucid Contributors"
!define DESCRIPTION "Spotlight-style desktop AI assistant"
!define EXE "lucid.exe"

SetCompressor /SOLID lzma
Name "${APPNAME} ${VERSION}"
OutFile "..\dist\Lucid-Setup-${VERSION}.exe"
InstallDir "$PROGRAMFILES64\${APPNAME}"
InstallDirRegKey HKLM "Software\${APPNAME}" "Install_Dir"
RequestExecutionLevel admin

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install"
    SetOutPath "$INSTDIR"
    File /r "..\dist\lucid\*.*"

    CreateDirectory "$SMPROGRAMS\${APPNAME}"
    CreateShortCut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\${EXE}" 0
    CreateShortCut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\${EXE}" 0

    ; Optional autostart — off by default. Uncomment to enable.
    ; WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APPNAME}" "$INSTDIR\${EXE}"

    WriteRegStr HKLM "Software\${APPNAME}" "Install_Dir" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher" "${COMPANY}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$INSTDIR\uninstall.exe"

    WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

Section "Uninstall"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Run\${APPNAME}"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
    DeleteRegKey HKLM "Software\${APPNAME}"

    Delete "$DESKTOP\${APPNAME}.lnk"
    Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
    RMDir "$SMPROGRAMS\${APPNAME}"

    Delete "$INSTDIR\uninstall.exe"
    RMDir /r "$INSTDIR"
SectionEnd
