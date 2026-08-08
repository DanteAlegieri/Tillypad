# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['restaurant_os_agent.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['win32timezone', 'pyodbc', 'websockets', 'servicemanager', 'win32service', 'win32serviceutil', 'app.websocket_agent_client', 'app.agent_diagnostics', 'app.service_manager', 'app.sql_autodetect', 'app.payload_codec', 'app.query_cache', 'http.server', 'app.local_agent_web', 'app.agent_state', 'app.agent_config'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RestaurantOSAgent_30_0_0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
)
