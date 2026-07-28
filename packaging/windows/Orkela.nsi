Unicode true
ManifestDPIAware true
ManifestSupportedOS all

!include "MUI2.nsh"
!include "LogicLib.nsh"

!ifndef ORKELA_VERSION
  !error "ORKELA_VERSION must be defined"
!endif
!ifndef ORKELA_ARCH
  !error "ORKELA_ARCH must be defined"
!endif
!ifndef ORKELA_SOURCE_EXE
  !error "ORKELA_SOURCE_EXE must be defined"
!endif
!ifndef ORKELA_OUTPUT_FILE
  !error "ORKELA_OUTPUT_FILE must be defined"
!endif

!define PRODUCT_NAME "Orkela"
!define PRODUCT_PUBLISHER "SceneLith Project"
!define PRODUCT_WEB_SITE "https://github.com/moshkinyevhen/orkela"
!define PRODUCT_UPDATE_URL \
  "https://github.com/moshkinyevhen/orkela/releases/latest"
!define PRODUCT_REG_KEY "Software\SceneLith\Orkela"
!define PRODUCT_UNINSTALL_KEY \
  "Software\Microsoft\Windows\CurrentVersion\Uninstall\Orkela"
!define PRODUCT_PROG_ID "Orkela.Resonith"

Name "${PRODUCT_NAME}"
Caption "${PRODUCT_NAME} ${ORKELA_VERSION} (${ORKELA_ARCH})"
OutFile "${ORKELA_OUTPUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\Orkela"
InstallDirRegKey HKCU "${PRODUCT_REG_KEY}" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show
BrandingText "Orkela · SceneLith Project"

VIProductVersion "0.3.0.6"
VIAddVersionKey /LANG=1033 "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey /LANG=1033 "CompanyName" "${PRODUCT_PUBLISHER}"
VIAddVersionKey /LANG=1033 "FileDescription" \
  "${PRODUCT_NAME} ${ORKELA_ARCH} installer"
VIAddVersionKey /LANG=1033 "FileVersion" "${ORKELA_VERSION}"
VIAddVersionKey /LANG=1033 "ProductVersion" "${ORKELA_VERSION}"
VIAddVersionKey /LANG=1033 "LegalCopyright" \
  "Copyright (c) 2026 SceneLith Project contributors"

!define MUI_ABORTWARNING
!define MUI_ICON "..\..\resources\orkela.ico"
!define MUI_UNICON "..\..\resources\orkela.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\Orkela.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch Orkela"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Function .onInit
  SetShellVarContext current
FunctionEnd

Function un.onInit
  SetShellVarContext current
FunctionEnd

Section "Orkela" CoreSection
  SectionIn RO
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  SetOverwrite on

  File /oname=Orkela.exe "${ORKELA_SOURCE_EXE}"
  File "..\..\README.md"
  File "..\..\CHANGELOG.md"
  File "..\..\VERSION"

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "${PRODUCT_REG_KEY}" \
    "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${PRODUCT_REG_KEY}" \
    "Version" "${ORKELA_VERSION}"
  WriteRegStr HKCU "${PRODUCT_REG_KEY}" \
    "Architecture" "${ORKELA_ARCH}"
  WriteRegStr HKCU "${PRODUCT_REG_KEY}" \
    "UpdateUrl" "${PRODUCT_UPDATE_URL}"

  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" \
    "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" \
    "DisplayVersion" "${ORKELA_VERSION}"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" \
    "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" \
    "DisplayIcon" "$INSTDIR\Orkela.exe"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" \
    "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" \
    "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" \
    "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" \
    "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" \
    "URLUpdateInfo" "${PRODUCT_UPDATE_URL}"
  WriteRegDWORD HKCU "${PRODUCT_UNINSTALL_KEY}" \
    "NoModify" 1
  WriteRegDWORD HKCU "${PRODUCT_UNINSTALL_KEY}" \
    "NoRepair" 1

  WriteRegStr HKCU "Software\Classes\${PRODUCT_PROG_ID}" \
    "" "Resonith audio"
  WriteRegStr HKCU "Software\Classes\${PRODUCT_PROG_ID}\DefaultIcon" \
    "" "$INSTDIR\Orkela.exe,0"
  WriteRegStr HKCU "Software\Classes\${PRODUCT_PROG_ID}\shell\open\command" \
    "" '"$INSTDIR\Orkela.exe" "%1"'
  WriteRegStr HKCU "Software\Classes\.resonith\OpenWithProgids" \
    "${PRODUCT_PROG_ID}" ""

  CreateDirectory "$SMPROGRAMS\Orkela"
  CreateShortcut "$SMPROGRAMS\Orkela\Orkela.lnk" \
    "$INSTDIR\Orkela.exe"
  CreateShortcut "$SMPROGRAMS\Orkela\Uninstall Orkela.lnk" \
    "$INSTDIR\Uninstall.exe"

  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd

Section "Uninstall"
  SetShellVarContext current

  Delete "$SMPROGRAMS\Orkela\Orkela.lnk"
  Delete "$SMPROGRAMS\Orkela\Uninstall Orkela.lnk"
  RMDir "$SMPROGRAMS\Orkela"

  DeleteRegKey HKCU "${PRODUCT_UNINSTALL_KEY}"
  DeleteRegKey HKCU "${PRODUCT_REG_KEY}"
  DeleteRegValue HKCU "Software\Classes\.resonith\OpenWithProgids" \
    "${PRODUCT_PROG_ID}"
  DeleteRegKey HKCU "Software\Classes\${PRODUCT_PROG_ID}"

  Delete "$INSTDIR\Orkela.exe"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\CHANGELOG.md"
  Delete "$INSTDIR\VERSION"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd
