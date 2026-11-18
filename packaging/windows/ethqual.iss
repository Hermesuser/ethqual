[Setup]
AppId={{8D4F6A2E-1B3C-4E9A-9F21-7C8A9E5B2D10}
AppName=ethqual
AppVersion=0.2.0
AppPublisher=ethqual
DefaultDirName={autopf}\ethqual
DefaultGroupName=ethqual
AllowNoIcons=yes
OutputDir=..\..\dist
OutputBaseFilename=ethqual-setup-windows-x64
SetupIconFile=..\..\ethqual\assets\icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\ethqual.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ethqual"; Filename: "{app}\ethqual.exe"
Name: "{autodesktop}\ethqual"; Filename: "{app}\ethqual.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ethqual.exe"; Description: "{cm:LaunchProgram,ethqual}"; Flags: nowait postinstall skipifsilent
