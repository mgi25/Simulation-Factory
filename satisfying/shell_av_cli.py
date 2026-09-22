"""Build, render, mux, and audit Category 3 Test #2 A/V previews.

The command copies Phase 1's already-recorded playback JSON.  It never calls
the simulator.  Godot and the score builder are then given the same copied
file, and a sync audit checks their identities and event placement.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Sequence

from satisfying import shell_audio, shell_av, shell_playback, shell_score


ROOT = Path(__file__).resolve().parents[1]
GODOT_PROJECT = ROOT / "godot"
RENDER_SCENE = "res://scenes/ShellEscapeRender.tscn"
DEFAULT_OUT = ROOT / "output" / "category3_shell_av_v3"
DEFAULT_EVIDENCE = ROOT / "docs" / "validation" / "category3_shell_av_v3"
PHASE1 = ROOT / "docs" / "validation" / "category3_shell_escape"


class AVCLIError(RuntimeError):
    pass


def _json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1) + "\n", encoding="utf-8")
    return path


def _playback(out: Path, seed: int) -> Path:
    return out / "playback" / f"seed_{seed}.json"


def _score(out: Path, seed: int) -> Path:
    return out / "scores" / f"seed_{seed}_refined_hybrid.score.json"


def _wav(out: Path, seed: int) -> Path:
    return out / "wav" / f"seed_{seed}_refined_hybrid.wav"


def _measure(out: Path, seed: int) -> Path:
    return out / "measurements" / f"seed_{seed}_refined_hybrid.measure.json"


def _frames(out: Path, seed: int, quality: str) -> Path:
    return out / "frames" / quality / f"seed_{seed}"


def _audit(out: Path, seed: int, quality: str) -> Path:
    return out / "audits" / quality / f"seed_{seed}" / "audit.json"


def _preview(out: Path, seed: int, quality: str) -> Path:
    return out / "previews" / quality / f"seed_{seed}_av_{quality}.mp4"


def _source_playback(seed: int) -> Path:
    return PHASE1 / f"phase1_playback_seed{seed}.json"


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _seeds(values: Sequence[int] | None) -> tuple[int, ...]:
    seeds = tuple(values or shell_av.CANDIDATE_SEEDS)
    unknown = sorted(set(seeds) - set(shell_av.CANDIDATE_SEEDS))
    if unknown:
        raise AVCLIError(f"outside the four-seed integration cast: {unknown}")
    return seeds


def task_prepare(args: argparse.Namespace) -> int:
    out, evidence = Path(args.out), Path(args.evidence)
    for seed in _seeds(args.seeds):
        source = _source_playback(seed)
        if not source.is_file():
            raise AVCLIError(f"missing recorded Phase 1 playback: {source}")
        document = _load(source)
        verification = shell_playback.verify_document(document)
        if not all(value for key, value in verification.items()
                   if key.endswith("_matches")):
            raise AVCLIError(f"playback verification failed for {seed}: {verification}")
        shell_av.validate_shared_document(document)
        target = _playback(out, seed)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        before = json.dumps(document, sort_keys=True, separators=(",", ":"))
        plan = shell_score.schedule(document, shell_score.named_config("refined_hybrid"))
        rendered = shell_audio.render(plan)
        after = json.dumps(document, sort_keys=True, separators=(",", ":"))
        if before != after:
            raise AVCLIError(f"audio mutated playback seed {seed}")
        score = plan.as_dict()
        score["score_fingerprint"] = plan.fingerprint()
        measurement = shell_audio.measure(rendered)
        identity = shell_av.identity(document)
        _json(_score(out, seed), score)
        _wav(out, seed).parent.mkdir(parents=True, exist_ok=True)
        shell_audio.write_master(rendered, os.fspath(_wav(out, seed)))
        _json(_measure(out, seed), measurement)
        _json(evidence / "scores" / _score(out, seed).name, score)
        _json(evidence / "measurements" / _measure(out, seed).name, measurement)
        _json(evidence / "identity" / f"seed_{seed}.identity.json", identity)
        print(
            f"seed {seed}: playback {document['digest'][:16]}  "
            f"score {plan.fingerprint()[:16]}  PCM {rendered.digest()[:16]}"
        )
    _json(evidence / "integration_config.json", {
        "format": shell_av.INTEGRATION_VERSION,
        "candidate_seeds": list(shell_av.CANDIDATE_SEEDS),
        "config": shell_av.CONFIG.as_dict(),
        "config_digest": shell_av.CONFIG.fingerprint(),
    })
    return 0


def _find_godot(explicit: str | None) -> str:
    candidates = [explicit] if explicit else []
    candidates.extend(filter(None, (
        os.environ.get("GODOT4"), os.environ.get("GODOT"),
        shutil.which("godot4"), shutil.which("godot"),
    )))
    # The repository's Phase 2A worktree keeps the validated portable build.
    candidates.append(os.fspath(
        ROOT.parent / "Simulation Factory-category3-shell-visual-v2a" /
        ".tools" / "godot" / "bin" / "Godot_v4.7.2-stable_win64_console.exe"
    ))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    raise AVCLIError("cannot find Godot 4; pass --godot PATH")


def _find_ffmpeg(explicit: str | None) -> str:
    candidate = explicit or shutil.which("ffmpeg")
    if candidate and (os.path.isfile(candidate) or shutil.which(candidate)):
        return os.path.abspath(candidate) if os.path.isfile(candidate) else str(shutil.which(candidate))
    raise AVCLIError("cannot find ffmpeg; pass --ffmpeg PATH")


def _profile(quality: str) -> tuple[int, int, int, int]:
    config = shell_av.CONFIG
    if quality == "review":
        return config.review_width, config.review_height, config.review_fps, config.review_crf
    if quality == "full":
        return config.full_width, config.full_height, config.full_fps, config.full_crf
    raise AVCLIError(f"unknown quality {quality}")


def _run(command: Sequence[str], label: str, cwd: Path = ROOT) -> str:
    started = time.time()
    result = subprocess.run(
        list(command), cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode:
        tail = "\n".join((result.stdout + "\n" + result.stderr).splitlines()[-40:])
        raise AVCLIError(f"{label} exited {result.returncode}\n{tail}")
    for line in result.stderr.splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise AVCLIError(f"{label}: {line}")
    print(f"{label}: {time.time() - started:.1f}s")
    return result.stdout


def _godot(args: argparse.Namespace, seed: int, quality: str, audit: bool) -> None:
    godot = _find_godot(args.godot)
    width, height, fps, _ = _profile(quality)
    target = _audit(Path(args.out), seed, quality).parent if audit else _frames(
        Path(args.out), seed, quality
    )
    target.mkdir(parents=True, exist_ok=True)
    command = [
        godot, "--path", os.fspath(GODOT_PROJECT), RENDER_SCENE, "--",
        f"--playback={_playback(Path(args.out), seed).resolve().as_posix()}",
        f"--out-dir={target.resolve().as_posix()}",
        f"--width={width}", f"--height={height}", f"--fps={fps}",
        "--audit=1" if audit else "--clip=1",
    ]
    stdout = _run(command, f"Godot {quality} {'audit' if audit else 'render'} seed {seed}")
    for line in stdout.splitlines():
        if line.strip().startswith(("playback seed", "arena ", "frame ", "audit ")):
            print("  " + line.strip())


def task_render(args: argparse.Namespace) -> int:
    for seed in _seeds(args.seeds):
        _godot(args, seed, args.quality, False)
    return 0


def task_audit(args: argparse.Namespace) -> int:
    out, evidence = Path(args.out), Path(args.evidence)
    _, _, fps, _ = _profile(args.quality)
    for seed in _seeds(args.seeds):
        _godot(args, seed, args.quality, True)
        document = _load(_playback(out, seed))
        report = shell_av.sync_audit(document, _load(_audit(out, seed, args.quality)), fps)
        _json(out / "sync" / args.quality / f"seed_{seed}.sync.json", report)
        _json(evidence / "sync" / args.quality / f"seed_{seed}.sync.json", report)
        print(
            f"seed {seed}: max {report['maximum_sync_error_seconds'] * 1000:.3f} ms "
            f"({report['maximum_sync_error_frames']:.6f} frame), "
            f"{'PASS' if report['pass'] else 'FAIL'}"
        )
        if not report["pass"]:
            return 1
    return 0


def _ffprobe(ffmpeg: str, path: Path) -> dict[str, Any]:
    probe = Path(ffmpeg).with_name("ffprobe.exe")
    executable = os.fspath(probe if probe.is_file() else "ffprobe")
    result = subprocess.run(
        [executable, "-v", "error", "-show_streams", "-show_format", "-of", "json", os.fspath(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode:
        raise AVCLIError(f"ffprobe failed for {path}: {result.stderr}")
    return json.loads(result.stdout)


def task_mux(args: argparse.Namespace) -> int:
    out, evidence = Path(args.out), Path(args.evidence)
    ffmpeg = _find_ffmpeg(args.ffmpeg)
    _, _, fps, crf = _profile(args.quality)
    for seed in _seeds(args.seeds):
        frames = sorted(_frames(out, seed, args.quality).glob("frame_*.png"))
        if not frames:
            raise AVCLIError(f"no rendered frames for seed {seed} {args.quality}")
        audio = _wav(out, seed)
        if not audio.is_file():
            raise AVCLIError(f"no rendered audio for seed {seed}")
        target = _preview(out, seed, args.quality)
        target.parent.mkdir(parents=True, exist_ok=True)
        command = [
            ffmpeg, "-y", "-framerate", str(fps), "-start_number", "0",
            "-i", os.fspath(_frames(out, seed, args.quality) / "frame_%06d.png"),
            "-i", os.fspath(audio),
            "-filter_complex", "[0:v]tpad=stop_mode=clone:stop_duration=1[v]",
            "-map", "[v]", "-map", "1:a:0", "-c:v", shell_av.CONFIG.video_codec,
            "-preset", shell_av.CONFIG.preset, "-crf", str(crf),
            "-pix_fmt", shell_av.CONFIG.pixel_format,
            "-c:a", shell_av.CONFIG.audio_codec, "-b:a", shell_av.CONFIG.audio_bitrate,
            "-ar", str(shell_av.CONFIG.audio_sample_rate), "-movflags", "+faststart",
            "-shortest", os.fspath(target),
        ]
        _run(command, f"mux {args.quality} seed {seed}")
        probe = _ffprobe(ffmpeg, target)
        _json(out / "delivery" / args.quality / f"seed_{seed}.probe.json", probe)
        _json(evidence / "delivery" / args.quality / f"seed_{seed}.probe.json", probe)
        print(f"  {target} ({target.stat().st_size / 1_048_576:.1f} MB, {len(frames)} frames)")
    return 0


def task_listening(args: argparse.Namespace) -> int:
    """Write explicit mono and phone-like checks from the uncompressed master."""
    out = Path(args.out)
    ffmpeg = _find_ffmpeg(args.ffmpeg)
    for seed in _seeds(args.seeds):
        source = _wav(out, seed)
        folder = out / "listening"
        folder.mkdir(parents=True, exist_ok=True)
        mono = folder / f"seed_{seed}_mono.wav"
        phone = folder / f"seed_{seed}_phone.wav"
        _run([ffmpeg, "-y", "-i", os.fspath(source), "-ac", "1", os.fspath(mono)],
             f"mono check seed {seed}")
        _run([
            ffmpeg, "-y", "-i", os.fspath(source), "-ac", "1",
            "-af", "highpass=f=300,lowpass=f=3500,volume=-6dB", os.fspath(phone),
        ], f"phone check seed {seed}")
    return 0


def task_metrics(args: argparse.Namespace) -> int:
    out, evidence = Path(args.out), Path(args.evidence)
    records = []
    for seed in _seeds(args.seeds):
        record = shell_av.experience_metrics(_load(_playback(out, seed)))
        records.append(record)
        _json(evidence / "experience" / f"seed_{seed}.experience.json", record)
    _json(out / "experience_comparison.json", {"candidates": records})
    _json(evidence / "experience_comparison.json", {"candidates": records})
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("task", choices=("prepare", "render", "audit", "mux", "listening", "metrics"))
    result.add_argument("--out", default=os.fspath(DEFAULT_OUT))
    result.add_argument("--evidence", default=os.fspath(DEFAULT_EVIDENCE))
    result.add_argument("--seeds", nargs="*", type=int)
    result.add_argument("--quality", choices=("review", "full"), default="review")
    result.add_argument("--godot")
    result.add_argument("--ffmpeg")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int({
        "prepare": task_prepare,
        "render": task_render,
        "audit": task_audit,
        "mux": task_mux,
        "listening": task_listening,
        "metrics": task_metrics,
    }[args.task](args))


if __name__ == "__main__":
    raise SystemExit(main())
