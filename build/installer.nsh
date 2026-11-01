; Default install location on D: so the app body does not land on C:.
; The user can still change it in the installer because
; allowToChangeInstallationDirectory is enabled. If the machine has no D:
; drive, keep electron-builder's default (per-user AppData) instead of
; writing a path the installer cannot create.
!macro preInit
  SetRegView 64
  IfFileExists "D:\*.*" 0 price_monitor_default_dir_done
    WriteRegExpandStr HKCU "${INSTALL_REGISTRY_KEY}" InstallLocation "D:\PriceMonitor\App"
  price_monitor_default_dir_done:
!macroend

; Electron registers the login item at runtime; remove it on uninstall so a
; deleted executable is not launched at the next sign-in.
!macro customUnInstall
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "com.pricemonitor.app"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "PriceMonitor"
!macroend
