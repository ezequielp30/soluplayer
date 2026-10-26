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
; Instalación solo para el usuario actual: no pide permisos de administrador. Sin el cuadro «para todos
; los usuarios»: con él, al instalar con la cuenta de un administrador los datos y ajustes que limpia el
; desinstalador serían los del administrador, no los del usuario (se puede forzar con /ALLUSERS).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
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
; En Configuración → Aplicaciones → Aplicaciones predeterminadas (para elegirlo como reproductor de cada tipo).
Root: HKA; Subkey: "Software\Clients\Media\{#ProgId}"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Clients\Media\{#ProgId}\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#AppName}"; Tasks: openwith
Root: HKA; Subkey: "Software\Clients\Media\{#ProgId}\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Reproductor de archivos de audio locales"; Tasks: openwith
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#AppName}"; ValueData: "Software\Clients\Media\{#ProgId}\Capabilities"; Flags: uninsdeletevalue; Tasks: openwith
#include "extensiones.iss"
#include "papelera.iss"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName} ahora"; Flags: nowait postinstall skipifsilent

[Code]
// Al desinstalar: la biblioteca (playlists, respaldos, ajustes) se conserva salvo que el usuario diga lo
// contrario, y aun así va a la Papelera de reciclaje (se puede recuperar), nunca se borra para siempre.
// Si queda otra copia del programa instalada (p. ej. una «para todos los usuarios» y otra «solo para mí»),
// ni se pregunta: esa otra copia usa la misma biblioteca. Las canciones (archivos de audio) nunca se tocan.

function OtherCopyInstalled(): Boolean;
var
  Candidates: array of String;
  I: Integer;
  This: String;
begin
  Result := False;
  This := ExpandConstant('{app}\{#AppExe}');
  SetArrayLength(Candidates, 3);
  Candidates[0] := ExpandConstant('{localappdata}\Programs\ReproductorMusica\{#AppExe}');
  Candidates[1] := ExpandConstant('{commonpf64}\ReproductorMusica\{#AppExe}');
  Candidates[2] := ExpandConstant('{commonpf32}\ReproductorMusica\{#AppExe}');
  for I := 0 to GetArrayLength(Candidates) - 1 do
    if FileExists(Candidates[I]) and (CompareText(Candidates[I], This) <> 0) then
      Result := True;
end;

function SetEnvironmentVariable(lpName: String; lpValue: String): BOOL;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

// packaging\papelera.ps1 (incrustado por crear-instalador.ps1 en papelera.iss): envía la carpeta a la
// Papelera y, si algo no se puede reciclar (no cabe, o la Papelera está desactivada), Windows PREGUNTA
// antes de borrarlo para siempre. La carpeta va en una variable de entorno: sin problemas de comillas.
function SendToRecycleBin(const Dir: String): Boolean;
var
  ResultCode: Integer;
begin
  SetEnvironmentVariable('REPRO_PAPELERA_DIR', Dir);
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
                 '-NoProfile -NonInteractive -EncodedCommand {#PapeleraCmd}',
                 '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
            and (ResultCode = 0) and not DirExists(Dir);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\ReproductorMusica');
    if not DirExists(DataDir) or UninstallSilent then
      Exit;
    if OtherCopyInstalled() then
    begin
      MsgBox('En este equipo queda otra copia del Reproductor de Música instalada, que usa la misma ' +
             'biblioteca: tu biblioteca y tus playlists se conservan.', mbInformation, MB_OK);
      Exit;
    end;
    if MsgBox('¿Quieres borrar también tu biblioteca del reproductor?' + #13#10 + #13#10 +
              'Se enviarían a la Papelera de reciclaje tus playlists, títulos corregidos, respaldos y ' +
              'ajustes del programa (se pueden recuperar desde la Papelera).' + #13#10 +
              'Tus archivos de música NO se borran en ningún caso, y la copia de tus playlists en ' +
              'Documentos\Reproductor de Música tampoco.' + #13#10 + #13#10 +
              'Si vas a volver a instalar el programa, elige «No»: todo se conserva.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      if SendToRecycleBin(DataDir) then
        RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\ReproductorMusica')
      else
        MsgBox('No se pudo enviar toda la biblioteca a la Papelera. Lo que quedó sigue en:' + #13#10 + DataDir + #13#10 +
               '(si algo llegó a enviarse, está en la Papelera de reciclaje).', mbError, MB_OK);
    end;
  end;
end;
