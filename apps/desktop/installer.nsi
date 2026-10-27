; Private reviewed candidate. Compile using the pinned NSIS SDK; no elevated setup.
Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"
!ifndef PRODUCT_VERSION
!error "Pass the exact reviewed product version"
!endif
!ifndef PAYLOAD
!error "Pass an audited target-specific payload directory"
!endif
!ifndef PAYLOAD_MANIFEST_SHA
!error "Bind the exact installed file manifest"
!endif
!ifndef OUTPUT_FILE
!error "Pass an output outside the source checkout"
!endif
Name "Literature Review Engine"
OutFile "${OUTPUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\Literature Review Engine"
RequestExecutionLevel user
SetCompressor zlib
ShowInstDetails show
ShowUninstDetails show
BrandingText "Experimental Windows beta — not yet tested on Windows"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TEXT "Experimental Windows beta — not yet tested on Windows. Install the local research application for this user. Core runtimes are bundled; research data stays outside the application. This unsigned candidate is for reviewed testing only. Do not bypass Windows security warnings."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\app-${PRODUCT_VERSION}\LiteratureReviewEngine.exe"
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  SetShellVarContext current
  ; AMD64=9. Explicitly reject ARM64 and 32-bit native operating systems.
  System::Alloc 64
  Pop $0
  System::Call 'kernel32::GetNativeSystemInfo(p r0)'
  System::Call '*$0(&i2 .r1)'
  System::Free $0
  IntCmp $1 9 x64 unsupported unsupported
  unsupported:
    MessageBox MB_ICONSTOP "This candidate targets Windows 11 x64 only. Windows ARM and 32-bit Windows are not supported."
    Abort
  x64:
  ; RtlGetVersion observes the real build, independent of compatibility shims.
  System::Alloc 284
  Pop $0
  System::Call '*$0(i 284)'
  System::Call 'ntdll::RtlGetVersion(p r0)i.r1'
  System::Call '*$0(i, i.r2, i.r3, i.r4)'
  System::Free $0
  IntCmp $1 0 version_read failed_version failed_version
  failed_version:
    MessageBox MB_ICONSTOP "Windows version could not be verified. Nothing was installed."
    Abort
  version_read:
  IntCmp $2 10 check_build unsupported_version unsupported_version
  check_build:
  IntCmp $4 22000 version_ok unsupported_version version_ok
  unsupported_version:
    MessageBox MB_ICONSTOP "This private candidate targets Windows 11 x64. Other Windows versions are unqualified."
    Abort
  version_ok:
  SetRegView 64
  Call ValidateRoot
  IfFileExists "$INSTDIR\*" 0 new_install_root
    ReadINIStr $0 "$INSTDIR\.litrev-install.ini" "Product" "ID"
    StrCmp $0 "org.hnt119.litrev.desktop" +3
      MessageBox MB_ICONSTOP "An unrecognized folder already uses this application path. Its contents were preserved; inspect it before installing."
      Abort
    ReadRegStr $0 HKCU "Software\hnt119\LiteratureReviewEngineDesktop" "InstallRoot"
    StrCmp $0 $INSTDIR +3
      MessageBox MB_ICONSTOP "The existing folder has no matching per-user installation record. Nothing was changed."
      Abort
  new_install_root:
  Call RequireClosed
FunctionEnd

!macro RootGuard PREFIX
Function ${PREFIX}ValidateRoot
  GetFullPathName $0 "$LOCALAPPDATA\Programs\Literature Review Engine"
  GetFullPathName $1 "$INSTDIR"
  StrCmp $0 $1 +3
    MessageBox MB_ICONSTOP "Only this user's fixed Programs application directory is accepted. No research directory was changed."
    Abort
  StrCpy $INSTDIR $0
  StrCpy $2 $0
  root_loop_${PREFIX}:
    System::Call 'kernel32::GetFileAttributesW(w r2)i.r3'
    IntCmp $3 -1 root_parent_${PREFIX}
    IntOp $4 $3 & 1024
    IntCmp $4 0 root_parent_${PREFIX}
      MessageBox MB_ICONSTOP "Installation paths cannot contain links or reparse points. Nothing was changed."
      Abort
  root_parent_${PREFIX}:
    ${GetParent} "$2" $3
    StrCmp $3 $2 root_done_${PREFIX}
    StrCmp $3 "" root_done_${PREFIX}
    StrCpy $2 $3
    Goto root_loop_${PREFIX}
  root_done_${PREFIX}:
FunctionEnd
!macroend
!insertmacro RootGuard ""
!insertmacro RootGuard "un."

Function RequireClosed
  ; Exclusive image/lock opening catches startup before any window exists.
  IfFileExists "$LOCALAPPDATA\LiteratureReviewEngineDesktop\engine\.desktop-backend.lock" 0 no_backend_lock
    System::Call 'kernel32::CreateFileW(w "$LOCALAPPDATA\LiteratureReviewEngineDesktop\engine\.desktop-backend.lock",i 0x80000000,i 0,p 0,i 3,i 0x00200000,p 0)p.r0'
    IntCmp $0 -1 busy
    System::Call 'kernel32::CloseHandle(p r0)'
  no_backend_lock:
  FindFirst $5 $6 "$INSTDIR\app-*"
  close_loop:
    StrCmp $6 "" close_done
    IfFileExists "$INSTDIR\$6\LiteratureReviewEngine.exe" 0 next_version
      System::Call 'kernel32::CreateFileW(w "$INSTDIR\$6\LiteratureReviewEngine.exe",i 0xC0000000,i 0,p 0,i 3,i 0x00200000,p 0)p.r0'
      IntCmp $0 -1 busy_close
      System::Call 'kernel32::CloseHandle(p r0)'
    IfFileExists "$INSTDIR\$6\resources\python\python.exe" 0 next_version
      System::Call 'kernel32::CreateFileW(w "$INSTDIR\$6\resources\python\python.exe",i 0xC0000000,i 0,p 0,i 3,i 0x00200000,p 0)p.r0'
      IntCmp $0 -1 busy_close
      System::Call 'kernel32::CloseHandle(p r0)'
  next_version:
    FindNext $5 $6
    Goto close_loop
  close_done:
    FindClose $5
    Return
  busy_close:
    FindClose $5
  busy:
    MessageBox MB_ICONSTOP "Save and quit Literature Review Engine before changing the installation. Nothing was stopped."
    Abort
FunctionEnd

Function un.onInit
  SetShellVarContext current
  SetRegView 64
  Call un.ValidateRoot
  ReadRegStr $0 HKCU "Software\hnt119\LiteratureReviewEngineDesktop" "InstallRoot"
  StrCmp $0 $INSTDIR +3
    MessageBox MB_ICONSTOP "This uninstaller does not match the registered per-user application directory. Nothing was removed."
    Abort
  ReadINIStr $0 "$INSTDIR\.litrev-install.ini" "Product" "ID"
  StrCmp $0 "org.hnt119.litrev.desktop" +3
    MessageBox MB_ICONSTOP "The owned installation marker is missing. Nothing was removed."
    Abort
  IfFileExists "$INSTDIR\app-${PRODUCT_VERSION}\INSTALLATION.json" +3
    MessageBox MB_ICONSTOP "The exact installed-version manifest is missing. Nothing was removed."
    Abort
FunctionEnd

Section "Application"
  Call ValidateRoot
  Call RequireClosed
  SetShellVarContext current
  SetRegView 64
  ; The reviewed stdlib-only helper executes from a temporary bundled runtime,
  ; before any application executable is unpacked into its final location.
  InitPluginsDir
  SetOutPath "$PLUGINSDIR\python"
  File /r "${PAYLOAD}\resources\python\*"
  SetOutPath "$PLUGINSDIR"
  File "${PAYLOAD}\resources\engine\scripts\desktop_install_root.py"
  nsExec::ExecToStack '"$PLUGINSDIR\python\python.exe" -I -S -B "$PLUGINSDIR\desktop_install_root.py" "$INSTDIR" "${PRODUCT_VERSION}"'
  Pop $0
  Pop $1
  StrCmp $0 0 +3
    MessageBox MB_ICONSTOP "The fixed directory is unsafe, its ACL could not be verified, or this exact app version already exists. Preserve your data and uninstall that version before reinstalling. Nothing was unpacked there."
    Abort
  ; Version-specific application files avoid overwriting another running version.
  SetOutPath "$INSTDIR\app-${PRODUCT_VERSION}"
  File /r "${PAYLOAD}\*"
  CreateDirectory "$SMPROGRAMS\Literature Review Engine"
  CreateShortcut "$SMPROGRAMS\Literature Review Engine\Literature Review Engine.lnk" "$INSTDIR\app-${PRODUCT_VERSION}\LiteratureReviewEngine.exe"
  WriteINIStr "$INSTDIR\.litrev-install.ini" "Product" "ID" "org.hnt119.litrev.desktop"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateShortcut "$SMPROGRAMS\Literature Review Engine\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\hnt119\LiteratureReviewEngineDesktop" "InstallRoot" "$INSTDIR"
  WriteRegStr HKCU "Software\hnt119\LiteratureReviewEngineDesktop\Versions" "${PRODUCT_VERSION}" "${PAYLOAD_MANIFEST_SHA}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\org.hnt119.litrev.desktop" "DisplayName" "Literature Review Engine"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\org.hnt119.litrev.desktop" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\org.hnt119.litrev.desktop" "Publisher" "hnt119"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\org.hnt119.litrev.desktop" "InstallLocation" "$INSTDIR\app-${PRODUCT_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\org.hnt119.litrev.desktop" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\org.hnt119.litrev.desktop" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\org.hnt119.litrev.desktop" "NoRepair" 1
SectionEnd

Section "Uninstall"
  Call un.ValidateRoot
  SetShellVarContext current
  SetRegView 64
  ; Execute the bundled isolated interpreter from NSIS's temporary directory so
  ; its original payload files can be removed without scheduling a reboot.
  InitPluginsDir
  CopyFiles /SILENT "$INSTDIR\app-${PRODUCT_VERSION}\resources\python" "$PLUGINSDIR"
  CopyFiles /SILENT "$INSTDIR\app-${PRODUCT_VERSION}\resources\engine\scripts\desktop_uninstall.py" "$PLUGINSDIR\desktop_uninstall.py"
  nsExec::ExecToStack '"$PLUGINSDIR\python\python.exe" -I -S -B "$PLUGINSDIR\desktop_uninstall.py" "$INSTDIR"'
  Pop $0
  Pop $1
  StrCmp $0 0 +3
    MessageBox MB_ICONSTOP "Application validation or owned-process checks failed. Save and quit the app, then retry. Nothing outside verified application files is removed."
    Abort
  DetailPrint "$1"
  Delete "$SMPROGRAMS\Literature Review Engine\Literature Review Engine.lnk"
  Delete "$SMPROGRAMS\Literature Review Engine\Uninstall.lnk"
  RMDir "$SMPROGRAMS\Literature Review Engine"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\org.hnt119.litrev.desktop"
  DeleteRegKey HKCU "Software\hnt119\LiteratureReviewEngineDesktop"
  Delete "$INSTDIR\.litrev-install.ini"
  Delete "$INSTDIR\Uninstall.exe"
  ; Non-recursive only: unexpected or modified files always survive.
  RMDir "$INSTDIR"
SectionEnd
