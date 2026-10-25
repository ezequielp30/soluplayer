; Instalador de Reproductor de Música (Inno Setup 6).
; No lo compiles a mano: usa crear-instalador.ps1, que pasa la versión y genera extensiones.iss.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "Reproductor de Música"
#define AppExe "ReproductorMusica.exe"
#define ProgId "ReproductorMusica.Audio"
#define AppAuthor "Ezequiel Perez"
#define AppEmail "ezequielp30@gmail.com"

[Setup]
AppId={{6F3A2C1E-9B4D-4E7A-8C2F-5D1B7A9E3C40}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppAuthor}
AppContact={#AppEmail}
AppPublisherURL=mailto:{#AppEmail}
AppSupportURL=mailto:{#AppEmail}
AppCopyright=© 2026 {#AppAuthor} · GNU GPL versión 3 o posterior
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppAuthor}
; Página «Antes de instalar»: aviso de uso bajo propia responsabilidad (se lee y se continúa con «Siguiente»).
InfoBeforeFile=aviso.txt
; Instalación solo para el usuario actual: no pide permisos de administrador.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\ReproductorMusica
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=..\assets\icono.ico
WizardStyle=modern
OutputDir=..\build\instalador
OutputBaseFilename=Instalar-ReproductorMusica-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Windows 10 1809 o posterior (requisito de Qt 6).
MinVersion=10.0.17763
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el &Escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked
Name: "openwith"; Description: "Agregar «{#AppName}» a «Abrir con» para archivos de música (no cambia tu programa predeterminado)"; GroupDescription: "Integración con Windows:"

[InstallDelete]
; Al actualizar se borra la carpeta interna de la versión anterior: si no, quedarían bibliotecas y
; complementos viejos mezclados con los nuevos y el programa podría no abrir. Los datos del usuario
; (biblioteca, playlists, ajustes) están en %LOCALAPPDATA% y no se tocan.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\codigo-fuente"

[Files]
Source: "..\build\dist\ReproductorMusica\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Código fuente del programa (GPL) y de FFmpeg (LGPL): viajan con el instalador (crear-instalador.ps1).
Source: "{#SourceZip}"; DestDir: "{app}\codigo-fuente"; Flags: ignoreversion
Source: "{#FFmpegSource}"; DestDir: "{app}\codigo-fuente"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Tipo de archivo propio para «Abrir con» (en HKCU porque la instalación es por usuario).
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueData: "Archivo de audio"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExe},0"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: openwith
#include "extensiones.iss"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName} ahora"; Flags: nowait postinstall skipifsilent

[Code]
// Al desinstalar: la biblioteca (playlists, respaldos, ajustes) se conserva salvo que el usuario
// diga lo contrario. Las canciones (archivos de audio) nunca se tocan.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\ReproductorMusica');
    if DirExists(DataDir) and not UninstallSilent then
    begin
      if MsgBox('¿Borrar también tu biblioteca del reproductor?' + #13#10 + #13#10 +
                'Se borrarían tus playlists, correcciones de datos, respaldos y ajustes.' + #13#10 +
                'Tus archivos de música NO se borran en ningún caso.' + #13#10 + #13#10 +
                'Si eliges «No», todo se conserva y volverá a aparecer si reinstalas el programa.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
        RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\ReproductorMusica');
      end;
    end;
  end;
end;
