; ---------------------------------------------------------------------------
; Image Classifier Installer
; Always shows Select Destination → Installation Options → Ready to Install
; ---------------------------------------------------------------------------

#define MyAppName      "Image Classifier"
; MyAppVersion: synced from version.txt by scripts/update_iss_version.py before release
#ifndef MyAppVersion
  #define MyAppVersion "2.0.1"
#endif
#define MyAppPublisher "Francisco Villanueva"
#define MyAppURL       "https://imageclassifier.neocities.org/"
#define MyAppExeName   "Image Classifier.exe"
#define MyCertFile     "imageclassifier_cert.cer"
#define MyCertSubject  "Image Classifier Self‑Signed"
#define ReadmeFile     "README.txt"

[Setup]
AppId={{DFEE49F5-577E-407C-9DE6-28DBAF2D28F9}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
DisableProgramGroupPage=yes
OutputBaseFilename=ImageClassifierSetup_v{#MyAppVersion}
SetupIconFile=star.ico
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
; Run‑page descriptions
english.LaunchProgram=Launch {#MyAppName}
spanish.LaunchProgram=Lanzar {#MyAppName}
english.OpenReadme=Open README
spanish.OpenReadme=Abrir README
english.VisitWebsite=Visit website
spanish.VisitWebsite=Visitar sitio web

; Certificate prompt
english.CertPromptHeader=To ensure Windows trusts this application, a security certificate must be installed.
english.CertPromptQuestion=Install now?
spanish.CertPromptHeader=Para que Windows confíe en esta aplicación, debe instalarse un certificado de seguridad.
spanish.CertPromptQuestion=¿Instalar ahora?

; Installation Options page
english.OptionsTitle=Installation Options
spanish.OptionsTitle=Opciones de instalación
english.OptionsMsg=Select any additional actions you’d like the installer to perform:
spanish.OptionsMsg=Seleccione las acciones adicionales que desea realizar:
english.AVWarningHead=⚠ Third‑party non‑Windows Defender antivirus detected.
spanish.AVWarningHead=⚠ Antivirus distinto de Windows Defender detectado.
english.AVWarningSub=Exclude the installation folder in your antivirus manually to avoid false positives.
spanish.AVWarningSub=Excluya la carpeta de instalación en su antivirus manualmente para evitar falsos positivos.
english.ExcludeDefender=Exclude installation folder from Windows Defender
english.ExcludeDefenderAlready=Installation folder already excluded from Windows Defender ✅
spanish.ExcludeDefender=Agregar carpeta de instalación a las exclusiones de Windows Defender
spanish.ExcludeDefenderAlready=Carpeta de instalación excluida en Windows Defender ✅
english.DefenderDisabled=Windows Defender disabled.
spanish.DefenderDisabled=Windows Defender deshabilitado.
english.CreateDesktopIcon=Create Desktop icon
spanish.CreateDesktopIcon=Crear un acceso directo en el Escritorio

[Files]
Source: "installer\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "installer\{#MyCertFile}";   DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "installer\{#ReadmeFile}";   DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}";   Description: "{cm:LaunchProgram}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#ReadmeFile}";    Description: "{cm:OpenReadme}";    Flags: shellexec postinstall skipifsilent unchecked
Filename: "explorer.exe";           Parameters: """{#MyAppURL}""";  Description: "{cm:VisitWebsite}"; Flags: shellexec postinstall skipifsilent unchecked

[UninstallRun]
Filename: "certutil.exe"; Parameters: "-delstore root ""{#MyCertSubject}""";       Flags: runhidden
Filename: "certutil.exe"; Parameters: "-delstore root -user ""{#MyCertSubject}"""; Flags: runhidden

[UninstallDelete]
Type: files; Name: "{userdesktop}\{#MyAppName}.lnk"

[Code]
//--------------------------------------------------------------------------
// Wrapper around certutil.exe
//--------------------------------------------------------------------------  
function ExecCertUtil(const Params: String): Boolean;
var
  Code: Integer;
begin
  Exec('certutil.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, Code);
  Result := (Code = 0);
end;

//--------------------------------------------------------------------------
// Returns True if our certificate is already installed
//--------------------------------------------------------------------------  
function IsCertInstalled(): Boolean;
begin
  Result :=
    ExecCertUtil('-verifystore root "' + ExpandConstant('{#MyCertSubject}') + '"')
    or ExecCertUtil('-verifystore root -user "' + ExpandConstant('{#MyCertSubject}') + '"');
end;

//--------------------------------------------------------------------------
// Returns True if Windows Defender is enabled
//--------------------------------------------------------------------------  
function IsDefenderEnabled(): Boolean;
var
  DValue: Cardinal;
begin
  if RegQueryDWordValue(
       HKLM64,
       'SOFTWARE\Microsoft\Windows Defender',
       'DisableAntiSpyware',
       DValue
     ) then
    Result := (DValue = 0)
  else
    Result := True;
end;

//--------------------------------------------------------------------------
// Returns True if the given path is already excluded
//--------------------------------------------------------------------------  
function IsFolderExcluded(const Path: String): Boolean;
begin
  Result :=
    RegValueExists(
      HKLM64,
      'SOFTWARE\Microsoft\Windows Defender\Exclusions\Paths',
      Path
    )
    or
    RegValueExists(
      HKCU64,
      'SOFTWARE\Microsoft\Windows Defender\Exclusions\Paths',
      Path
    );
end;

var
  UsesDefender, ThirdPartyAV: Boolean;
  OptionsPage: TWizardPage;
  ExclCheck, IconCheck: TNewCheckBox;
  AVHead, AVSub: TNewStaticText;

//--------------------------------------------------------------------------
// InitializeWizard: run once before any pages are shown
//--------------------------------------------------------------------------  
procedure InitializeWizard();
var
  title, msg: String;
  y: Integer;
  installPath: String;
begin
  // 1) Detect whether Defender is on, and if any known 3rd‑party AV is present
  UsesDefender := IsDefenderEnabled();
  ThirdPartyAV :=
    RegKeyExists(HKLM64,'SOFTWARE\AVAST Software')
    or RegKeyExists(HKLM64,'SOFTWARE\Bitdefender')
    or RegKeyExists(HKLM64,'SOFTWARE\ESET')
    or RegKeyExists(HKLM64,'SOFTWARE\McAfee');

  // 2) Always insert our custom "Installation Options" page right after the built‑in SelectDir
  title := ExpandConstant('{cm:OptionsTitle}');
  msg   := ExpandConstant('{cm:OptionsMsg}');
  OptionsPage := CreateCustomPage(wpSelectDir, title, msg);
  y := ScaleY(8);

  // Get the folder the user will install into (default or edited)
  installPath := WizardForm.DirEdit.Text;

  // 3a) If we detect a 3rd‑party AV, show a two‑line warning
  if ThirdPartyAV then
  begin
    AVHead := TNewStaticText.Create(WizardForm);
    AVHead.Parent := OptionsPage.Surface;
    AVHead.Font.Style := AVHead.Font.Style + [fsBold];
    AVHead.Caption := ExpandConstant('{cm:AVWarningHead}');
    AVHead.SetBounds(0, y, OptionsPage.Surface.Width, ScaleY(20));
    AVSub := TNewStaticText.Create(WizardForm);
    AVSub.Parent   := OptionsPage.Surface;
    AVSub.WordWrap := True;
    AVSub.Caption  := ExpandConstant('{cm:AVWarningSub}');
    AVSub.SetBounds(
      ScaleX(16),
      AVHead.Top + AVHead.Height + ScaleY(4),
      OptionsPage.Surface.Width - ScaleX(16),
      ScaleY(32)
    );
    y := AVSub.Top + AVSub.Height + ScaleY(6);
  end
  // 3b) Else if Defender is on AND the path isn't already excluded, show the checkbox
  else if UsesDefender and not IsFolderExcluded(installPath) then
  begin
    ExclCheck := TNewCheckBox.Create(WizardForm);
    ExclCheck.Parent  := OptionsPage.Surface;
    ExclCheck.Caption := ExpandConstant('{cm:ExcludeDefender}');
    ExclCheck.Checked := True;
    ExclCheck.SetBounds(0, y, OptionsPage.Surface.Width, ScaleY(30));
    y := ExclCheck.Top + ExclCheck.Height + ScaleY(6);
  end
  // 3c) Otherwise (Defender off or already excluded), show a static message
  else
  begin
    AVHead := TNewStaticText.Create(WizardForm);
    AVHead.Parent := OptionsPage.Surface;
    AVHead.Font.Style := AVHead.Font.Style + [fsBold];
    if not UsesDefender then
      AVHead.Caption := ExpandConstant('{cm:DefenderDisabled}')
    else
      AVHead.Caption := ExpandConstant('{cm:ExcludeDefenderAlready}');
    AVHead.SetBounds(0, y, OptionsPage.Surface.Width, ScaleY(20));
    y := AVHead.Top + AVHead.Height + ScaleY(6);
  end;

  // 4) Finally, always add the desktop‑icon checkbox below
  IconCheck := TNewCheckBox.Create(WizardForm);
  IconCheck.Parent  := OptionsPage.Surface;
  IconCheck.Caption := ExpandConstant('{cm:CreateDesktopIcon}');
  IconCheck.Checked := False;
  IconCheck.SetBounds(0, y, OptionsPage.Surface.Width, ScaleY(30));
end;

//--------------------------------------------------------------------------
// CurPageChanged: when the Ready page comes up, append the user’s selections
//--------------------------------------------------------------------------  
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpReady then
  begin
    WizardForm.ReadyMemo.Lines.Add('');
    WizardForm.ReadyMemo.Lines.Add('Additional actions:');
    if Assigned(ExclCheck) and ExclCheck.Checked then
      WizardForm.ReadyMemo.Lines.Add('  • ' + ExclCheck.Caption);
    if Assigned(IconCheck) and IconCheck.Checked then
      WizardForm.ReadyMemo.Lines.Add('  • ' + IconCheck.Caption);
  end;
end;

//--------------------------------------------------------------------------
// CurStepChanged: after files are installed, apply the chosen options
//--------------------------------------------------------------------------  
procedure CurStepChanged(CurStep: TSetupStep);
var
  Choice: Integer;
  Header, Question: String;
begin
  if CurStep <> ssPostInstall then Exit;

  // Apply Defender exclusion if they checked it
  if Assigned(ExclCheck) and ExclCheck.Checked then
    Exec(
      'powershell.exe',
      '-NoProfile -Command "Set-MpPreference -ExclusionPath ''' +
        ExpandConstant('{app}') + '''"',
      '', SW_HIDE, ewWaitUntilTerminated, Choice
    );

  // Create desktop icon if they checked the last box
  if Assigned(IconCheck) and IconCheck.Checked then
  try
    CreateShellLink(
      ExpandConstant('{userdesktop}\{#MyAppName}.lnk'),
      '{#MyAppName}',
      ExpandConstant('{app}\{#MyAppExeName}'),
      '', '', '', 0, SW_SHOWNORMAL
    );
  except
    MsgBox('Warning: failed to create desktop icon.', mbInformation, MB_OK);
  end;

  // Prompt for certificate install
  if not IsCertInstalled() then
  begin
    Header   := ExpandConstant('{cm:CertPromptHeader}');
    Question := ExpandConstant('{cm:CertPromptQuestion}');
    if MsgBox(Header + #13#10#13#10 + Question, mbConfirmation, MB_YESNO) = IDYES then
    begin
      ExecCertUtil('-addstore root "' + ExpandConstant('{tmp}\{#MyCertFile}') + '"');
      ExecCertUtil('-addstore root -user "' + ExpandConstant('{tmp}\{#MyCertFile}') + '"');
    end;
  end;
end;

//--------------------------------------------------------------------------
// Confirm before uninstall
//--------------------------------------------------------------------------  
function InitializeUninstall(): Boolean;
begin
  Result := MsgBox(
    'Are you sure you want to uninstall Image Classifier and delete all files?'#13#10+
    '(This will remove the application completely.)',
    mbConfirmation, MB_YESNO
  ) = IDYES;
end;

//--------------------------------------------------------------------------
// Cleanup on uninstall: remove icon, local data & Defender exclusion
//--------------------------------------------------------------------------  
procedure DeinitializeUninstall();
var
  Code: Integer;
  Lnk: String;
begin
  Lnk := ExpandConstant('{userdesktop}\{#MyAppName}.lnk');
  if FileExists(Lnk) then DeleteFile(Lnk);
  DelTree(ExpandConstant('{localappdata}\{#MyAppName}'), True, True, True);
  Exec(
    'powershell.exe',
    '-NoProfile -Command "Remove-MpPreference -ExclusionPath ''' +
      ExpandConstant('{app}') + '''"',
    '', SW_HIDE, ewWaitUntilTerminated, Code
  );
end;
