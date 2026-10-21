"""Pilot steps 3-4: separate each preview into stems with Demucs (htdemucs,
4 stems) and embed the mix and every stem with MuQ-MuLan.

Per song, for each of STEMS (the full mix is kept as its own "stem" - it
carries the atmosphere / space of the whole production):
  - MuQ-MuLan embedding (512-d) of the rating excerpt and of the full preview
  - RMS level in dBFS, for silent-stem gating
  - MFCC mean+std (40-d) of the excerpt, a classic interpretable timbre
    baseline
The excerpt of the mix and each stem is also written as OGG for the rating
app, so the listener hears exactly what the model embedded.

The htdemucs checkpoint is loaded from Ultimate Vocal Remover's model folder
when present (same official weights), else downloaded by demucs.

Run with the research venv:
  research/stem_similarity/.venv/Scripts/python research/stem_similarity/embed_stems.py
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import librosa
import numpy as np
import pandas as pd
import soundfile as sf
import torch
import torchaudio.functional as AF
from demucs.apply import apply_model
from demucs.pretrained import get_model
from muq import MuQMuLan

HERE = Path(__file__).resolve().parent
AUDIO_DIR = HERE / "audio"
CLIP_DIR = HERE / "audio" / "clips"
SONGS_PATH = HERE / "pilot_songs.csv"
OUT_PATH = HERE / "embeddings" / "pilot_embeddings.npz"
CACHE_DIR = HERE / "embeddings" / "per_song"

UVR_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ultimate Vocal Remover"
UVR_DEMUCS_REPO = UVR_DIR / "models" / "Demucs_Models" / "v3_v4_repo"
UVR_FFMPEG = UVR_DIR / "ffmpeg.exe"

STEMS = ["mix", "drums", "bass", "vocals", "other"]
EXCERPT = (10.0, 20.0)  # seconds within the 30 s preview - what the listener rates
MUQ_SR = 24_000
N_MFCC = 20

device = "cuda" if torch.cuda.is_available() else "cpu"


def load_audio(path):
    """(channels=2, samples) float32 at the file's rate; ffmpeg fallback."""
    try:
        wav, sr = sf.read(path, dtype="float32", always_2d=True)
        wav = wav.T
    except Exception:
        sr = 44_100
        raw = subprocess.run(
            [str(UVR_FFMPEG), "-v", "quiet", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(sr), "-"],
            capture_output=True,
            check=True,
        ).stdout
        wav = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T
    if wav.shape[0] == 1:
        wav = np.repeat(wav, 2, axis=0)
    return wav, sr


def load_demucs():
    if (UVR_DEMUCS_REPO / "htdemucs.yaml").exists():
        print(f"Using htdemucs from UVR: {UVR_DEMUCS_REPO}")
        model = get_model("htdemucs", repo=UVR_DEMUCS_REPO)
    else:
        model = get_model("htdemucs")
    return model.to(device).eval()


def separate(model, wav, sr):
    """Returns {stem: (2, samples)} at the model's rate, plus the resampled mix."""
    x = torch.from_numpy(wav).to(device)
    if sr != model.samplerate:
        x = AF.resample(x, sr, model.samplerate)
    ref = x.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    with torch.no_grad():
        out = apply_model(model, ((x - mean) / std)[None], device=device, split=True, overlap=0.25)[0]
    out = out * std + mean
    stems = {name: out[i] for i, name in enumerate(model.sources)}
    stems["mix"] = x
    return stems


def rms_db(x):
    return float(20 * torch.log10(x.pow(2).mean().sqrt() + 1e-9))


def embed_song(track_id, demucs, mulan):
    """All per-song outputs as a dict of arrays; writes the excerpt clips."""
    sr = demucs.samplerate
    wav, file_sr = load_audio(AUDIO_DIR / f"{track_id}.mp3")
    if wav.shape[1] / file_sr < EXCERPT[1]:
        raise ValueError(f"preview is {wav.shape[1] / file_sr:.1f} s, shorter than the excerpt window")
    stems = separate(demucs, wav, file_sr)
    a, b = (int(s * sr) for s in EXCERPT)
    out = {"rms_excerpt": [], "rms_full": [], "mfcc_excerpt": []}
    full_mono, excerpt_mono = [], []
    for name in STEMS:
        x = stems[name]
        ex = x[:, a:b]
        out["rms_full"].append(rms_db(x))
        out["rms_excerpt"].append(rms_db(ex))
        sf.write(CLIP_DIR / f"{track_id}_{name}.ogg", ex.T.cpu().numpy(), sr, format="OGG")
        full_mono.append(AF.resample(x.mean(0), sr, MUQ_SR))
        excerpt_mono.append(AF.resample(ex.mean(0), sr, MUQ_SR))
        mf = librosa.feature.mfcc(y=ex.mean(0).cpu().numpy(), sr=sr, n_mfcc=N_MFCC)
        out["mfcc_excerpt"].append(np.r_[mf.mean(1), mf.std(1)])
    with torch.no_grad():
        out["emb_excerpt"] = mulan(wavs=torch.stack(excerpt_mono)).cpu().numpy()
        length = min(len(w) for w in full_mono)
        out["emb_full"] = mulan(wavs=torch.stack([w[:length] for w in full_mono])).cpu().numpy()
    return {key: np.asarray(v, np.float32) for key, v in out.items()}


def main():
    songs = pd.read_csv(SONGS_PATH)
    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    demucs = load_demucs()
    mulan = MuQMuLan.from_pretrained("OpenMuQ/MuQ-MuLan-large").to(device).eval()

    n, k = len(songs), len(STEMS)
    arrays = {
        "emb_excerpt": np.zeros((n, k, 512), np.float32),
        "emb_full": np.zeros((n, k, 512), np.float32),
        "rms_excerpt": np.zeros((n, k), np.float32),
        "rms_full": np.zeros((n, k), np.float32),
        "mfcc_excerpt": np.zeros((n, k, 2 * N_MFCC), np.float32),
    }
    ok = np.zeros(n, bool)

    # Each song is cached as soon as it's done, so a crash or rerun resumes
    t0, computed = time.time(), 0
    for i, track_id in enumerate(songs["track_id"]):
        cache = CACHE_DIR / f"{track_id}.npz"
        if cache.exists():
            result = dict(np.load(cache))
        else:
            try:
                result = embed_song(track_id, demucs, mulan)
            except Exception as exc:
                print(f"  skip {track_id}: {exc}", flush=True)
                continue
            np.savez(cache, **result)
            computed += 1
            if computed % 10 == 0:
                rate = (time.time() - t0) / computed
                print(f"{i + 1}/{n} songs, {rate:.1f} s/song, ~{rate * (n - i - 1) / 60:.0f} min left", flush=True)
        for key, value in result.items():
            arrays[key][i] = value
        ok[i] = True

    np.savez(
        OUT_PATH,
        track_ids=songs["track_id"].to_numpy(),
        stems=np.array(STEMS),
        ok=ok,
        excerpt=np.array(EXCERPT),
        **arrays,
    )
    print(
        f"Embedded {ok.sum()}/{n} songs ({computed} computed now) in "
        f"{(time.time() - t0) / 60:.1f} min on {device} -> {OUT_PATH}"
    )


if __name__ == "__main__":
    sys.exit(main())
