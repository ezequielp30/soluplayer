"""Teclas multimedia del teclado (Reproducir/Pausa, Siguiente, Anterior, Detener) también con la ventana
minimizada o detrás de otra.

Qt solo las recibe con la ventana activa. Aquí se registran en Windows (RegisterHotKey) para la ventana
principal; si otro programa ya las tiene registradas, esa tecla queda como estaba (funciona con la
ventana activa) y no se le quita a nadie. Se puede apagar en Preferencias.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter
from PySide6.QtWidgets import QApplication

log = logging.getLogger(__name__)

_WM_HOTKEY = 0x0312
_MOD_NOREPEAT = 0x4000  # mantener la tecla apretada no la repite
_MESSAGE_OFFSET = wintypes.MSG.message.offset  # dónde está el número de mensaje dentro de MSG


class MediaKeys(QAbstractNativeEventFilter):
    PLAY_PAUSE_ID = 0x5201
    NEXT_ID = 0x5202
    PREVIOUS_ID = 0x5203
    STOP_ID = 0x5204
    _KEYS = {PLAY_PAUSE_ID: 0xB3, NEXT_ID: 0xB0, PREVIOUS_ID: 0xB1, STOP_ID: 0xB2}  # VK_MEDIA_*

    def __init__(self, hwnd: int, actions: dict[int, Callable[[], None]]) -> None:
        """`actions`: qué hacer con cada tecla (por su id: PLAY_PAUSE_ID, NEXT_ID…)."""
        super().__init__()
        self._hwnd = hwnd
        self._actions = actions
        self._registered: list[int] = []

    @property
    def registered(self) -> list[int]:
        return list(self._registered)

    def enable(self) -> None:
        user32 = ctypes.windll.user32
        for hotkey_id, vk in self._KEYS.items():
            if hotkey_id in self._registered or hotkey_id not in self._actions:
                continue
            if user32.RegisterHotKey(wintypes.HWND(self._hwnd), hotkey_id, _MOD_NOREPEAT, vk):
                self._registered.append(hotkey_id)
            else:
                log.info("La tecla multimedia %#x ya la usa otro programa: solo funcionará con la ventana activa", vk)

    def disable(self) -> None:
        user32 = ctypes.windll.user32
        for hotkey_id in self._registered:
            user32.UnregisterHotKey(wintypes.HWND(self._hwnd), hotkey_id)
        self._registered.clear()

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (nombre de Qt)
        # Se llama con cada mensaje de Windows: se mira primero solo el número de mensaje (barato).
        if bytes(event_type) != b"windows_generic_MSG":
            return False, 0
        if ctypes.c_uint.from_address(int(message) + _MESSAGE_OFFSET).value != _WM_HOTKEY:
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.hWnd != self._hwnd or msg.wParam not in self._actions:
            return False, 0
        if QApplication.activeModalWidget() is not None:
            # Hay una ventana de herramientas trabajando (convertir, ajustar volumen…): con el teclado
            # tampoco se puede tocar la reproducción, igual que con el mouse.
            return True, 0
        try:
            self._actions[msg.wParam]()
        except Exception:
            log.exception("Error al atender una tecla multimedia")
        return True, 0
