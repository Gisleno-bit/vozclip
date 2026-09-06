; Instalador de VozClip Escritor · Inno Setup 6
;
; Objetivo: que el usuario final haga doble clic y ya esté. Nada de
; elegir carpetas ni de leer opciones.
;
; PrivilegesRequired=lowest instala en la carpeta del usuario, así que
; NO aparece el aviso de control de cuentas de usuario. Un cuadro de
; diálogo de UAC es un obstáculo real para alguien que no ve la pantalla.

#define NombreApp     "VozClip Escritor"
#define VersionApp    "2.12.0"
#define Publicador    "Gisleno-bit"
#define UrlApp        "https://github.com/Gisleno-bit/vozclip"
#define EjecutableApp "VozClip.exe"

[Setup]
AppId={{7C4B2E10-9A3F-4D18-B6E2-1F5A8C0D3E71}
AppName={#NombreApp}
AppVersion={#VersionApp}
AppPublisher={#Publicador}
AppPublisherURL={#UrlApp}
AppSupportURL={#UrlApp}/issues

DefaultDirName={autopf}\VozClip
DefaultGroupName=VozClip
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
DisableWelcomePage=no

PrivilegesRequired=lowest
OutputDir=salida
OutputBaseFilename=VozClip-Instalador
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

; El instalador es accesible con lector de pantalla porque usa los
; controles estándar de Windows, que NVDA sí lee bien.
SetupLogging=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "..\dist\VozClip.exe";             DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\VozClip-Diagnostico.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LEEME.txt";                    DestDir: "{app}"; Flags: ignoreversion
Source: "..\GUIA_RAPIDA.txt";              DestDir: "{app}"; Flags: ignoreversion
Source: "..\scripts\instalar_modelos.bat";  DestDir: "{app}"; Flags: ignoreversion
Source: "..\scripts\instalar_en_inicio.bat"; DestDir: "{app}"; Flags: ignoreversion

; El modelo de voz, si la compilación lo pudo descargar. `skipifsourcedoesntexist`
; hace que el instalador se construya igual aunque la carpeta esté vacía.
; VozClip lo busca junto al ejecutable, así que con esto el dictado
; funciona desde el primer arranque, sin descargar nada.
Source: "..\modelos\*"; DestDir: "{app}\modelos"; \
        Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
; Escritorio: el acceso principal, siempre
Name: "{autodesktop}\VozClip Escritor"; Filename: "{app}\{#EjecutableApp}"; \
      Comment: "Editor de guiones que habla"

; Menú Inicio
Name: "{group}\VozClip Escritor";     Filename: "{app}\{#EjecutableApp}"
Name: "{group}\Diagnóstico de VozClip"; Filename: "{app}\VozClip-Diagnostico.exe"; \
      Comment: "Ejecuta esto si VozClip no funciona"

; El modelo de dictado (39 MB) no se empaqueta: multiplicaría el tamaño del
; instalador y no todo el mundo va a dictar. Se descarga desde aquí, una vez,
; con un .bat que habla en voz alta cada paso y pita al terminar.
Name: "{group}\Reinstalar el dictado por voz"; \
      Filename: "{app}\instalar_modelos.bat"; \
      Comment: "Solo si el dictado deja de funcionar: vuelve a descargar el modelo"

; Ya no hace falta un acceso directo en el escritorio para instalar el
; modelo: viene incluido. El del menú Inicio queda por si hay que
; reinstalarlo alguna vez.
Name: "{group}\Guía rápida";          Filename: "{app}\GUIA_RAPIDA.txt"
Name: "{group}\Desinstalar VozClip";  Filename: "{uninstallexe}"

; Arranque automático con Windows (opcional, marcado por defecto)
Name: "{userstartup}\VozClip Escritor"; Filename: "{app}\{#EjecutableApp}"; \
      Tasks: arranque

[Tasks]
Name: "arranque"; Description: "Arrancar VozClip al encender el ordenador"; \
      GroupDescription: "Opciones:"

[Run]
; Al terminar, abrir el programa. Habla solo, así que el usuario sabe
; inmediatamente que la instalación ha ido bien.
Filename: "{app}\{#EjecutableApp}"; \
    Description: "Abrir VozClip ahora"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; La configuración y los guiones NO se borran: son del usuario.
Type: filesandordirs; Name: "{app}"
