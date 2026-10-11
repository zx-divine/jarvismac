# Build on a real arm64 macOS Python only: python -m PyInstaller this-file.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
datas, binaries, hiddenimports = collect_all('vosk')
# Vosk's Mac wheel calls its Mach-O library libvosk.dyld. PyInstaller's
# generic *.dylib collector can classify that unusual suffix as data.
# Treat it as code so arm64 thinning and ad-hoc code signing are applied.
vosk_native = [(source, destination) for source, destination in datas
               if Path(source).name == 'libvosk.dyld']
datas = [(source, destination) for source, destination in datas
         if Path(source).name != 'libvosk.dyld']
binaries += vosk_native
datas += [(str(root / 'models/vosk-model-small-en-us-0.15'), 'models/vosk-model-small-en-us-0.15')]
a = Analysis([str(root / 'run_jarvis.py')], pathex=[str(root)], binaries=binaries,
             datas=datas, hiddenimports=hiddenimports, excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='JARVIS',
          debug=False, strip=False, upx=False, console=False, target_arch='arm64',
          codesign_identity=None, entitlements_file=None)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='JARVIS')
app = BUNDLE(collection, name='JARVIS.app', bundle_identifier='org.ash.jarvis',
             info_plist={'CFBundleShortVersionString': '0.2.0',
                         'NSPrincipalClass': 'NSApplication',
                         'NSHighResolutionCapable': True,
                         'NSMicrophoneUsageDescription': 'Recognize your approved local wake and sleep phrases and spoken commands. Hard Mute closes capture.',
                         'NSAppleEventsUsageDescription': 'Run individually approved Music, volume, and power actions using macOS automation.'})
