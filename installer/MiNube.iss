#ifndef MyAppVersion
  #define MyAppVersion "0.9.0"
#endif

#define MyAppName "Mi Nube"
#define MyAppExeName "MiNube.exe"

[Setup]
AppId={{8A2B913F-94F2-48DE-A2AD-84C32C9D5538}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Mi Nube
DefaultDirName={localappdata}\Programs\Mi Nube
DefaultGroupName=Mi Nube
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=MiNubeSetup
SetupIconFile=..\assets\mi_nube.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=yes
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription=Instalador de Mi Nube
VersionInfoProductName=Mi Nube

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "..\dist\MiNube\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Mi Nube"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Mi Nube"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Mi Nube"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if SuppressibleMsgBox(
      '¿Deseas eliminar también la sesión, configuración, portadas e historial local de Mi Nube?',
      mbConfirmation, MB_YESNO, IDNO) = IDYES then
      DelTree(ExpandConstant('{localappdata}\MiNube'), True, True, True);
  end;
end;
