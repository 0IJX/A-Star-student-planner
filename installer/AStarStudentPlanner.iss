#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName "A-Star Student Planner"
#define MyAppExeName "AStarStudentPlanner.exe"
#define MyAppPublisher "A-Star Student Planner Team"
#define MyOutputName "AStarStudentPlanner_Setup_" + MyAppVersion

[Setup]
AppId={{4A0D12F0-5E12-4FE5-8394-84C84FF5A4D3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\AStarStudentPlanner
DefaultGroupName=AStarStudentPlanner
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename={#MyOutputName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
PrivilegesRequired=lowest
LicenseFile=..\installer\LICENSE.txt
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Extra shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\AStarStudentPlanner\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\A-Star Student Planner"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\A-Star Student Planner"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\Uninstall A-Star Student Planner"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch A* Student Planner"; Flags: nowait postinstall skipifsilent

[Code]
function GetInstalledUninstallCommand(var Cmd: string): Boolean;
var
  KeyPath: string;
begin
  KeyPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1';
  Result := RegQueryStringValue(HKCU, KeyPath, 'UninstallString', Cmd);
end;

function InitializeSetup(): Boolean;
var
  UninstallCmd: string;
  Choice: Integer;
  ResultCode: Integer;
begin
  if GetInstalledUninstallCommand(UninstallCmd) then
  begin
    if WizardSilent then
      Choice := IDYES
    else
      Choice := MsgBox(
        'A-Star Student Planner is already installed.'#13#10#13#10 +
        'Yes: Reinstall (remove old version, then continue setup)'#13#10 +
        'No: Remove current install only and close setup'#13#10 +
        'Cancel: Keep current install and stop setup',
        mbConfirmation, MB_YESNOCANCEL);

    if Choice = IDCANCEL then
    begin
      Result := False;
      exit;
    end;

    if not Exec(RemoveQuotes(UninstallCmd), '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      MsgBox('Could not run old uninstaller. Please uninstall manually, then run setup again.', mbError, MB_OK);
      Result := False;
      exit;
    end;

    if Choice = IDNO then
    begin
      MsgBox('Old version removed. Setup will now close.', mbInformation, MB_OK);
      Result := False;
      exit;
    end;
  end;

  Result := True;
end;
