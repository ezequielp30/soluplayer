"""Audio generado para las pruebas: MP3 y WAV con forma de música (acordes, ruido y variaciones de volumen),
siempre iguales para la misma semilla. Así las pruebas no dependen de la música del usuario (que se mueve,
se borra o ya viene ajustada) y dan el mismo resultado en cualquier PC.

Las pruebas que además quieren probar con archivos reales de la biblioteca lo hacen solo si se pide:
MUSICPLAYER_PRUEBA_REAL=1 (ver usar_reales())."""
import os
import wave

import numpy as np

RATE = 44100


def usar_reales() -> bool:
    """¿Probar también con archivos reales de la biblioteca del usuario? (solo copias, nunca los originales)."""
    return os.environ.get("MUSICPLAYER_PRUEBA_REAL") == "1"


def music(seconds: float, peak: float = 0.5, seed: int = 0, rate: int = RATE, channels: int = 2) -> np.ndarray:
    """Señal estéreo (frames × canales, float) parecida a música: un acorde que cambia, algo de ruido y un
    volumen que sube y baja. `peak` es el pico de muestra que alcanza (0,1 = muy baja; 0,9 = muy fuerte)."""
    rng = np.random.default_rng(seed)
    n = int(rate * seconds)
    t = np.arange(n) / rate
    root = 110 * 2 ** (rng.integers(0, 12) / 12)
    chord = sum(np.sin(2 * np.pi * root * ratio * t + rng.uniform(0, 6)) / (k + 1)
                for k, ratio in enumerate((1, 1.25, 1.5, 2, 3)))
    noise = np.convolve(rng.standard_normal(n), np.ones(8) / 8, mode="same") * 0.3
    envelope = 0.6 + 0.4 * np.sin(2 * np.pi * rng.uniform(0.2, 0.6) * t)
    mono = (chord + noise) * envelope
    left = mono
    right = np.roll(mono, int(rate * 0.003)) * 0.95  # algo de imagen estéreo
    out = np.stack([left, right], axis=1)[:, :channels]
    return out / np.max(np.abs(out)) * peak


def mp3(path: str, seconds: float = 20, peak: float = 0.5, seed: int = 0, bitrate: int = 192,
        rate: int = RATE, channels: int = 2, title: str | None = None, artist: str = "Prueba") -> str:
    """MP3 generado con LAME, con etiquetas de título y artista."""
    import lameenc

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    pcm = (music(seconds, peak, seed, rate, channels) * 32767).astype("<i2")
    enc = lameenc.Encoder()
    enc.set_bit_rate(bitrate); enc.set_in_sample_rate(rate); enc.set_channels(channels); enc.set_quality(2)
    with open(path, "wb") as f:
        f.write(enc.encode(pcm.tobytes()) + enc.flush())
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3NoHeaderError

    try:
        tags = EasyID3(path)
    except ID3NoHeaderError:
        tags = EasyID3()
    tags["title"] = title or os.path.splitext(os.path.basename(path))[0]
    tags["artist"] = artist
    tags.save(path)
    return path


def wav(path: str, seconds: float = 6, peak: float = 0.5, seed: int = 0, rate: int = RATE, channels: int = 2) -> str:
    """WAV de 16 bits generado."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    pcm = (music(seconds, peak, seed, rate, channels) * 32767).astype("<i2")
    with wave.open(path, "wb") as f:
        f.setnchannels(channels); f.setsampwidth(2); f.setframerate(rate)
        f.writeframes(pcm.tobytes())
    return path
