; Default install location on D: so the app body does not land on C:.
; The user can still change it in the installer because
; allowToChangeInstallationDirectory is enabled.
!macro preInit
  SetRegView 64
  WriteRegExpandStr HKCU "${INSTALL_REGISTRY_KEY}" InstallLocation "D:\PriceMonitor\App"
!macroend
