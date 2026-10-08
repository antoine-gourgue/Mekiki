; The engine (mekiki-engine.exe) runs from the install folder, and Windows refuses to replace
; a running executable. An update closes the app abruptly, before its engine has stopped, so
; the installer stops it itself; the Python process the PyInstaller bootloader starts runs
; from the same file, hence /T.

!macro MEKIKI_STOP_ENGINE
  nsExec::Exec 'taskkill /F /T /IM mekiki-engine.exe'
  Pop $0
  ; 0: an engine was running. Windows needs a moment to release its executable.
  StrCmp $0 "0" 0 +2
    Sleep 1500
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro MEKIKI_STOP_ENGINE
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro MEKIKI_STOP_ENGINE
!macroend
