"""Lectura (solo lectura) del volumen general de Windows y del silencio del dispositivo de salida.

Sirve para avisar cuando la música suena en el programa pero Windows tiene el sonido
silenciado o a 0 %. Usa la API Core Audio (IAudioEndpointVolume) mediante ctypes, sin
dependencias extra. Nunca cambia el volumen: solo llama a métodos de lectura.
Ante cualquier fallo devuelve None (desconocido) en vez de dar un aviso falso.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import POINTER, byref, c_float, c_int, c_uint, c_void_p
from dataclasses import dataclass

_CLSCTX_ALL = 23
_E_RENDER, _E_MULTIMEDIA = 0, 1

# Posiciones en la tabla de métodos (vtable). 0-2 son QueryInterface/AddRef/Release.
_ENUM_GET_DEFAULT_ENDPOINT = 4  # IMMDeviceEnumerator::GetDefaultAudioEndpoint
_DEVICE_ACTIVATE = 3  # IMMDevice::Activate
_VOL_GET_MASTER_SCALAR = 9  # IAudioEndpointVolume::GetMasterVolumeLevelScalar
_VOL_GET_MUTE = 15  # IAudioEndpointVolume::GetMute
_RELEASE = 2


class _GUID(ctypes.Structure):
    _fields_ = [("d1", c_uint), ("d2", ctypes.c_ushort), ("d3", ctypes.c_ushort), ("d4", ctypes.c_ubyte * 8)]


def _guid(text: str) -> _GUID:
    guid = _GUID()
    ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), byref(guid))
    return guid


@dataclass(frozen=True)
class SystemVolume:
    percent: int
    muted: bool

    @property
    def silent(self) -> bool:
        return self.muted or self.percent == 0


def _method(obj: c_void_p, index: int, *argtypes):
    vtable = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    prototype = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)
    return prototype(vtable[index])


def _release(obj: c_void_p) -> None:
    if obj:
        ctypes.WINFUNCTYPE(c_uint, c_void_p)(ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents[_RELEASE])(obj)


def read_system_volume() -> SystemVolume | None:
    """Volumen y silencio del dispositivo de salida predeterminado, o None si no se puede saber."""
    if sys.platform != "win32":
        return None
    ole32 = ctypes.windll.ole32
    init = ole32.CoInitializeEx(None, 2)  # STA; si ya estaba inicializado devuelve S_FALSE o RPC_E_CHANGED_MODE
    enumerator, device, volume = c_void_p(), c_void_p(), c_void_p()
    try:
        clsid = _guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}")  # MMDeviceEnumerator
        iid_enum = _guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}")  # IMMDeviceEnumerator
        iid_vol = _guid("{5CDF2C82-841E-4546-9722-0CF74078229A}")  # IAudioEndpointVolume
        if ole32.CoCreateInstance(byref(clsid), None, _CLSCTX_ALL, byref(iid_enum), byref(enumerator)) != 0:
            return None
        get_default = _method(enumerator, _ENUM_GET_DEFAULT_ENDPOINT, c_int, c_int, POINTER(c_void_p))
        get_default(enumerator, _E_RENDER, _E_MULTIMEDIA, byref(device))
        activate = _method(device, _DEVICE_ACTIVATE, POINTER(_GUID), c_uint, c_void_p, POINTER(c_void_p))
        activate(device, byref(iid_vol), _CLSCTX_ALL, None, byref(volume))
        level, muted = c_float(), ctypes.c_int()
        _method(volume, _VOL_GET_MASTER_SCALAR, POINTER(c_float))(volume, byref(level))
        _method(volume, _VOL_GET_MUTE, POINTER(c_int))(volume, byref(muted))
        if not 0.0 <= level.value <= 1.0:
            return None
        return SystemVolume(percent=round(level.value * 100), muted=bool(muted.value))
    except OSError:
        return None  # HRESULT de error: el dispositivo no existe, el servicio de audio está detenido, etc.
    finally:
        for obj in (volume, device, enumerator):
            _release(obj)
        if init in (0, 1):  # S_OK / S_FALSE: equilibrar la inicialización
            ole32.CoUninitialize()
