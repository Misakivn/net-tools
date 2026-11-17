"""Sinh version_info.txt (thông tin hiện trong Properties của NetTools.exe) từ nettools.__version__."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from nettools import APP_NAME, __version__  # noqa: E402

nums = tuple(int(x) for x in __version__.split(".")) + (0,)
TEMPLATE = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('FileDescription', '{APP_NAME}'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{__version__}'),
      StringStruct('OriginalFilename', 'NetTools.exe')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
with open(os.path.join(ROOT, "version_info.txt"), "w", encoding="utf-8") as f:
    f.write(TEMPLATE)
print(f"version_info.txt -> {__version__}")
