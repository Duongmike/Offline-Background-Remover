#define MyAppName "Không biết gì đừng nói"
#define MyAppVersion GetEnv("APP_VERSION")
#if MyAppVersion == ""
  #error APP_VERSION is required. Run build_installer.bat instead of compiling installer.iss directly.
#endif
#define MyAppPublisher "Không biết gì đừng nói"
#define MyAppExeName "KhongBietGiDungNoi.exe"

[Setup]
AppId={{B6A3C0D4-8E67-4D5E-AF0B-24A7E19C5D32}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\KhongBietGiDungNoi
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=release
OutputBaseFilename=KhongBietGiDungNoi_Setup_{#MyAppVersion}
SetupIconFile=assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern dynamic
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Bộ cài {#MyAppName}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng ngoài màn hình Desktop"; GroupDescription: "Tùy chọn bổ sung:"; Flags: unchecked

[Files]
Source: "dist\KhongBietGiDungNoi\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: files; Name: "{app}\TachNenPro.exe"
Type: files; Name: "{group}\Tách Nền Pro.lnk"
Type: files; Name: "{autodesktop}\Tách Nền Pro.lnk"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Mở {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Messages]
SetupWindowTitle=Cài đặt - %1
UninstallAppFullTitle=Gỡ cài đặt %1
ButtonNext=&Tiếp theo >
ButtonInstall=&Cài đặt
ButtonCancel=Hủy
ButtonFinish=&Hoàn tất
ClickNext=Nhấn Tiếp theo để tiếp tục hoặc Hủy để thoát trình cài đặt.
WelcomeLabel1=Chào mừng bạn đến với trình cài đặt [name]
WelcomeLabel2=Trình hướng dẫn sẽ cài đặt [name/ver] trên máy tính.%n%nBạn nên đóng các ứng dụng khác trước khi tiếp tục.
SelectDirDesc=Bạn muốn cài [name] ở đâu?
SelectDirLabel3=Ứng dụng sẽ được cài vào folder sau.
ReadyLabel1=Trình cài đặt đã sẵn sàng cài [name] trên máy tính.
FinishedHeadingLabel=Hoàn tất cài đặt [name]
FinishedLabel=[name] đã được cài đặt thành công. Bạn có thể mở ứng dụng bằng shortcut đã tạo.
ConfirmUninstall=Bạn có chắc muốn gỡ hoàn toàn %1 và tất cả thành phần không?
UninstallStatusLabel=Vui lòng chờ trong khi %1 được gỡ khỏi máy tính.
