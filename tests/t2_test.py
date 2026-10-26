import os as _os, tempfile as _tf  # datos y ajustes de prueba aparte: nunca los del usuario
_os.environ["MUSICPLAYER_DATA_DIR"] = _tf.mkdtemp(prefix="mp_t_"); _os.environ["MUSICPLAYER_ORG"] = "ReproductorMusicaTest"
import os, sys, shutil
sys.path.insert(0, r"D:\soluplayer")
import numpy as np, lameenc
from PySide6.QtCore import QCoreApplication
from PySide6.QtMultimedia import QAudioFormat
app = QCoreApplication([])
from app import mp3gain
from app.audio_decode import decode_file
from mutagen.id3 import ID3, TIT2
from mutagen.apev2 import APEv2
D = sys.argv[1]
def make(name, rate, ch, kbps):
    t = np.arange(rate*6)/rate
    s = (0.05*np.sin(2*np.pi*440*t)*32767).astype("<i2")
    if ch == 2: s = np.column_stack([s, s]).ravel()
    e = lameenc.Encoder(); e.set_bit_rate(kbps); e.set_in_sample_rate(rate); e.set_channels(ch); e.set_quality(2)
    p = os.path.join(D, name)
    open(p, "wb").write(e.encode(s.tobytes()) + e.flush())
    return p
def dec(p, rate, ch):
    f = QAudioFormat(); f.setSampleRate(rate); f.setChannelCount(ch); f.setSampleFormat(QAudioFormat.SampleFormat.Float)
    out = []
    err = decode_file(p, f, lambda b: out.append(np.frombuffer(bytes(b.constData()), dtype=np.float32)))
    return err, np.concatenate(out) if out else np.array([])
for name, rate, ch, kbps in [("m1s.mp3",44100,2,192),("m1m.mp3",44100,1,128),("m2s.mp3",22050,2,64),("m2m.mp3",16000,1,32),("m25.mp3",11025,1,16)]:
    p = make(name, rate, ch, kbps)
    t = ID3(); t.add(TIT2(encoding=3, text="x")); t.save(p)
    raw = open(p,"rb").read()
    fr = mp3gain._frames(raw)
    info = mp3gain.inspect(p)
    e0, a0 = dec(p, rate, ch)
    mp3gain.apply_steps(p, 4)
    mp3gain.write_applied_steps(p, 4)
    e1, a1 = dec(p, rate, ch)
    r = np.abs(a1).max()/np.abs(a0).max()
    print(name, "frames", len(fr), "info", info, "ratio +4 steps (esperado 2.0):", round(float(r),4), "annot", mp3gain.read_applied_steps(p), e0, e1)
    mp3gain.apply_steps(p, -4); mp3gain.write_applied_steps(p, 0)
    print("   roundtrip identical:", open(p,"rb").read() == raw)
