#define MyAppName "Restaurant OS Relay Agent"
#define MyAppVersion "15.3.0"
#define MyAppPublisher "Gastrodom"
#define MyAppExeName "AgentManager.exe"

[Setup]
AppId={{E8646B46-8AF9-4E67-BDF8-15E3E755E7A2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Gastrodom\RelayAgent
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=output
OutputBaseFilename=RestaurantOS_RelayAgent_Setup_15_3
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName}
CreateUninstallRegKey=yes

[Files]
Source: "..\dist\AgentManager.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "agent.env.example"; DestDir: "{commonappdata}\Gastrodom\RelayAgent"; DestName: "agent.env"; Flags: onlyifdoesntexist
Source: "install_websocket_agent_service.ps1"; DestDir: "{app}\installer"; Flags: ignoreversion

[Dirs]
Name: "{commonappdata}\Gastrodom\RelayAgent"; Permissions: admins-full system-full
Name: "{commonappdata}\Gastrodom\RelayAgent\logs"; Permissions: admins-full system-full
Name: "{commonappdata}\Gastrodom\RelayAgent\cache"; Permissions: admins-full system-full

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\install_websocket_agent_service.ps1"""; Flags: runhidden waituntilterminated
Filename: "{app}\AgentManager.exe"; Description: "Настроить и проверить агент"; Flags: postinstall nowait skipifsilent

[Icons]
Name: "{group}\Restaurant OS Agent Manager"; Filename: "{app}\AgentManager.exe"; Check: ShouldCreateIcon

[Tasks]
Name: "startmenuicon"; Description: "Создать ярлык панели управления в меню Пуск"; Flags: unchecked

[Code]
function ShouldCreateIcon(): Boolean;
begin
  Result := WizardIsTaskSelected('startmenuicon');
end;
