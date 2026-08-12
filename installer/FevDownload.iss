; Fev Download - Installer
;
; Erzeugt FevDownloadSetup.exe: eine einzelne Datei, die alles mitbringt.
; Gebaut ueber build_installer.ps1, nicht direkt aufrufen - die Fassung kommt
; ueber /DAppVersion von dort.
;
; Was hier passiert und anderswo nicht mehr noetig ist:
;   - Programm nach %LOCALAPPDATA%\Programs\FevDownload legen
;   - FevDownloader.py in Resolves Scripts-Ordner kopieren  (bisher install_plugin.ps1)
;   - install.json schreiben                                 (bisher install_plugin.ps1)
;   - Verknuepfungen anlegen
;
; Bewusst ohne Admin-Rechte (PrivilegesRequired=lowest): Es wird nur in Ordner
; geschrieben, die dem Benutzer gehoeren. Kein UAC-Fenster, und Resolves
; Scripts-Ordner liegt ohnehin unter %APPDATA% des jeweiligen Benutzers.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define AppName        "Fev Download"
#define AppPublisher   "fezco"
#define AppExeName     "FevDownload.exe"
#define SourceDir      "..\dist\FevDownload"
#define ProjectDir     ".."

[Setup]
AppId={{8F3A7C21-5D4E-4B96-9E7A-1C2B3D4E5F60}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\FevDownload
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
; Ohne Admin-Rechte installieren - siehe Kopf.
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=FevDownloadSetup
SetupIconFile=..\assets\fevdl.ico
UninstallDisplayIcon={app}\{#AppExeName}
; Die ~330 MB sind zum grossen Teil ffmpeg und Qt und lassen sich gut
; zusammenpressen. Kostet Bauzeit, spart Ladezeit bei jedem, der es herunterlaedt.
;
; Bewusst 'max' und nicht 'ultra64': Letzteres arbeitet mit einem 256 MB grossen
; Woerterbuch, ISCC.exe ist aber ein 32-Bit-Programm und laeuft dabei
; zuverlaessig aus dem Speicher ("Out of memory", Abbruch kurz vor Schluss).
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=2
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Verknuepfung auf dem Desktop anlegen"; GroupDescription: "Zusaetzliche Verknuepfungen:"

[Files]
; Das gepackte Programm samt Python, Qt und yt-dlp.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; ffmpeg und ffprobe kommen NEBEN die .exe, nicht ins Paket - paths.py sucht
; sie im Ordner der .exe.
Source: "{#ProjectDir}\bin\ffmpeg.exe";  DestDir: "{app}\bin"; Flags: ignoreversion
Source: "{#ProjectDir}\bin\ffprobe.exe"; DestDir: "{app}\bin"; Flags: ignoreversion

Source: "{#ProjectDir}\assets\fevdl.ico"; DestDir: "{app}\assets"; Flags: ignoreversion

; Das Script fuer Resolve. Liegt zusaetzlich im Programmordner, damit es sich
; nach einer Resolve-Neuinstallation von Hand wiederherstellen laesst.
Source: "{#ProjectDir}\resolve\FevDownloader.py"; DestDir: "{app}\resolve"; Flags: ignoreversion
Source: "{#ProjectDir}\resolve\FevDownloader.py"; DestDir: "{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"; Flags: ignoreversion

Source: "{#ProjectDir}\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\fevdl.ico"
Name: "{group}\{#AppName} deinstallieren"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\fevdl.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Fev Download jetzt starten"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Das Script in Resolve gehoert zu dieser Installation und hat ohne sie keinen
; Sinn - es wuerde beim Aufruf nur eine Fehlermeldung schreiben.
Type: files; Name: "{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\FevDownloader.py"
Type: files; Name: "{localappdata}\FevDownloader\install.json"
Type: files; Name: "{localappdata}\FevDownloader\job.json"
Type: files; Name: "{localappdata}\FevDownloader\result.json"
Type: files; Name: "{localappdata}\FevDownloader\launcher.log"
; Heruntergeladene Videos bleiben bewusst liegen - sie gehoeren dem Nutzer.

[Code]

{ install.json sagt dem Script in Resolve, wo das Programm liegt. Bisher
  schrieb install_plugin.ps1 diese Datei; im Installer muss es von Hand
  geschehen.

  Zwei Fallen stecken darin:
    1. JSON kennt den Rueckstrich als Fluchtzeichen - Windows-Pfade muessen
       also verdoppelt werden, sonst liest Python 'C:\Users' als Steuerzeichen.
    2. Die Datei darf keine Byte-Reihenfolge-Marke tragen. SaveStringToFile
       schreibt ohne, das passt. }

procedure WriteInstallJson();
var
  AppDir: String;
  JsonPath: String;
  EscapedPath: String;
  Json: String;
  Message: String;
begin
  AppDir := ExpandConstant('{localappdata}\FevDownloader');
  if not DirExists(AppDir) then
    ForceDirectories(AppDir);

  EscapedPath := ExpandConstant('{app}');
  StringChangeEx(EscapedPath, '\', '\\', True);

  JsonPath := AppDir + '\install.json';
  Json :=
    '{' + #13#10 +
    '  "project_root": "' + EscapedPath + '",' + #13#10 +
    '  "installed": "' + GetDateTimeString('yyyy/mm/dd hh:nn:ss', '-', ':') + '",' + #13#10 +
    '  "version": "' + '{#AppVersion}' + '"' + #13#10 +
    '}' + #13#10;

  { Keine Zeile darf mit '#' beginnen - der Praeprozessor haelt sie sonst fuer
    eine Direktive und bricht ab. Zeilenumbrueche deshalb ans Zeilenende. }
  if not SaveStringToFile(JsonPath, Json, False) then
  begin
    Message := 'Die Datei install.json konnte nicht geschrieben werden:' + #13#10;
    Message := Message + JsonPath + #13#10 + #13#10;
    Message := Message + 'Fev Download laeuft trotzdem, laesst sich aber nicht ';
    Message := Message + 'aus DaVinci Resolve heraus starten.';
    MsgBox(Message, mbError, MB_OK);
  end;
end;

{ Resolve legt seinen Scripts-Ordner erst an, wenn es einmal gelaufen ist. Wer
  Fev Download vor Resolve installiert, haette sonst kein Menue-Eintrag - und
  wuesste nicht, warum. Der Ordner wird deshalb notfalls angelegt; Resolve
  liest ihn beim naechsten Start einfach mit. }

procedure EnsureResolveScriptsDir();
var
  ScriptsDir: String;
begin
  ScriptsDir := ExpandConstant('{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility');
  if not DirExists(ScriptsDir) then
    ForceDirectories(ScriptsDir);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    EnsureResolveScriptsDir()
  else if CurStep = ssPostInstall then
    WriteInstallJson();
end;

{ Beim Deinstallieren fragen, ob die Zwischenspeicher mit weg sollen. Die
  Vorschaubilder koennen ueber die Zeit einige hundert MB erreichen. }

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    AppDir := ExpandConstant('{localappdata}\FevDownloader');
    if DirExists(AppDir + '\thumbs') then
    begin
      if MsgBox('Sollen die gespeicherten Vorschaubilder ebenfalls entfernt werden?' + #13#10#13#10 +
                'Die heruntergeladenen Videos bleiben in jedem Fall erhalten.',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(AppDir + '\thumbs', True, True, True);
    end;
    { Nachgeladenes yt-dlp gehoert zur Installation und geht immer mit. }
    DelTree(AppDir + '\ytdlp', True, True, True);
  end;
end;
