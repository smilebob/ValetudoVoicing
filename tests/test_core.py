"""Unit tests for ValetudoVoicing core modules."""

from pathlib import Path
import tarfile
import wave
import numpy as np
import pytest
import soundfile as sf
from typer.testing import CliRunner

from valetudo_voicing.cli import app
from valetudo_voicing.discovery import VoiceCandidate, _build_youtube_queries, _score_youtube_entry
from valetudo_voicing.effects import VOICE_EFFECTS, apply_voice_effect
from valetudo_voicing.i18n import get_ui_lang, set_ui_lang, tr
from valetudo_voicing.jingles import JINGLES, apply_jingle
from valetudo_voicing.packager import build_pkg, compute_md5
from valetudo_voicing.robots import ROBOROCK_PROFILES, match_robot_model
from valetudo_voicing.sounds import ROBOROCK_S5_SOUNDS, build_default_script, get_script_name, load_script, save_script
from valetudo_voicing.tts import get_backend
from valetudo_voicing.tui import AppState
from valetudo_voicing.voices import delete_voice_profile, list_voice_profiles, load_voice_profile, save_voice_profile
from valetudo_voicing.youtube import extract_best_speech_segment


def _create_dummy_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 1600)


def test_default_script_roundtrip(tmp_path: Path) -> None:
    script = build_default_script(lang="fr")
    assert script["robot"] == "roborock_s5"
    assert "start.wav" in script["sounds"]
    assert "error1.wav" in script["sounds"]
    assert "water_tank_in.wav" not in script["sounds"]

    s7_script = build_default_script(lang="en", robot="roborock_s7")
    assert s7_script["robot"] == "roborock_s7"
    assert "water_tank_in.wav" in s7_script["sounds"]
    assert "empty_start.wav" in s7_script["sounds"]

    yaml_path = tmp_path / "voicepack.yaml"
    save_script(script, yaml_path)
    loaded = load_script(yaml_path)
    assert loaded == script


def test_voice_profile_crud(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VALETUDO_VOICING_HOME", str(tmp_path / "home"))
    src_wav = tmp_path / "ref.wav"
    _create_dummy_wav(src_wav)

    saved = save_voice_profile(
        name="glados",
        reference_wav=src_wav,
        source_url="https://youtube.com/watch?v=123",
        source_lang="en",
        isolated_vocals=True,
        duration_sec=12.5,
    )
    assert saved.reference_wav.exists()

    loaded = load_voice_profile("glados")
    assert loaded.name == "glados"
    assert loaded.isolated_vocals is True
    assert loaded.duration_sec == 12.5

    profiles = list_voice_profiles()
    assert [p.name for p in profiles] == ["glados"]

    delete_voice_profile("glados")
    assert list_voice_profiles() == []


def test_build_pkg_unencrypted(tmp_path: Path) -> None:
    wav_dir = tmp_path / "wavs"
    _create_dummy_wav(wav_dir / "start.wav")
    _create_dummy_wav(wav_dir / "stop.wav")

    out_pkg = tmp_path / "out.pkg"
    pkg_path, md5_hex = build_pkg(wav_dir, out_pkg, encrypt=False)

    assert pkg_path.exists()
    assert len(md5_hex) == 32
    assert md5_hex == compute_md5(pkg_path)

    with tarfile.open(pkg_path, "r:gz") as tar:
        names = sorted(tar.getnames())
        assert names == ["start.wav", "start_clean.wav", "stop.wav", "stop_clean.wav"]


def test_tts_backend_registry() -> None:
    assert get_backend("xtts").name == "xtts"
    assert get_backend("chatterbox").name == "chatterbox"
    with pytest.raises(ValueError):
        get_backend("unknown")


def test_cli_init_and_voices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VALETUDO_VOICING_HOME", str(tmp_path / "home"))
    runner = CliRunner()

    yaml_out = tmp_path / "pack.yaml"
    res = runner.invoke(app, ["init", str(yaml_out), "--lang", "fr"])
    assert res.exit_code == 0
    assert yaml_out.exists()

    res_voices = runner.invoke(app, ["voices"])
    assert res_voices.exit_code == 0


def test_discovery_scoring_and_queries() -> None:
    queries_fr = _build_youtube_queries("GLaDOS", "fr")
    assert any("GLaDOS" in q and "fr" in q for q in queries_fr)

    assert _score_youtube_entry("GLaDOS AI Cover Song", 120.0, "GLaDOS", "fr") is None
    assert _score_youtube_entry("GLaDOS", 3.0, "GLaDOS", "fr") is None
    good_score = _score_youtube_entry("GLaDOS voix VF répliques", 60.0, "GLaDOS", "fr")
    assert good_score is not None and good_score > 4.0


def test_extract_best_speech_segment(tmp_path: Path) -> None:
    sr = 24000
    # 10s silence + 15s synthetic speech-like tone + 10s silence = 35s total
    silence = np.zeros(10 * sr, dtype="float32")
    t = np.linspace(0, 15, 15 * sr, endpoint=False, dtype="float32")
    speech = 0.25 * np.sin(2 * np.pi * 220 * t)
    full = np.concatenate([silence, speech, silence])

    src_wav = tmp_path / "full.wav"
    out_wav = tmp_path / "best.wav"
    sf.write(str(src_wav), full, sr, subtype="PCM_16")

    dur = extract_best_speech_segment(src_wav, out_wav, target_min_sec=12.0, target_max_sec=25.0)
    assert out_wav.exists()
    assert 12.0 <= dur <= 25.0


def test_cli_learn_character_auto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VALETUDO_VOICING_HOME", str(tmp_path / "home"))
    fake_wav = tmp_path / "fake_ref.wav"
    _create_dummy_wav(fake_wav)

    class _DummyTmp:
        def cleanup(self) -> None:
            pass

    monkeypatch.setattr(
        "valetudo_voicing.cli.search_character_voices",
        lambda character, lang, limit=5: [
            VoiceCandidate(source="youtube", title=f"{character} VF", url="https://youtu.be/abc", duration_sec=45.0)
        ],
    )
    monkeypatch.setattr(
        "valetudo_voicing.cli.extract_youtube_voice",
        lambda url, start=None, end=None, isolate_vocals=False, auto_trim=False: (_DummyTmp(), fake_wav, 15.0),
    )

    runner = CliRunner()
    res = runner.invoke(app, ["learn", "--character", "GLaDOS", "--lang", "fr", "--auto"])
    assert res.exit_code == 0
    assert load_voice_profile("glados").name == "glados"


def test_cli_record_interactive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    script = build_default_script(lang="fr")
    # Keep only 2 sounds for quick test
    script["sounds"] = {
        "start.wav": script["sounds"]["start.wav"],
        "stop.wav": script["sounds"]["stop.wav"],
    }
    yaml_path = tmp_path / "rec.yaml"
    save_script(script, yaml_path)

    def fake_record(output_wav: Path, device: str = "default", sample_rate: int = 24000) -> float:
        _create_dummy_wav(output_wav)
        return 1.2

    def fake_norm(src_wav: Path, dst_wav: Path) -> None:
        _create_dummy_wav(dst_wav)

    monkeypatch.setattr("valetudo_voicing.cli.record_until_enter", fake_record)
    monkeypatch.setattr("valetudo_voicing.cli.trim_and_normalize_recording", fake_norm)
    monkeypatch.setattr("valetudo_voicing.cli.play_wav", lambda p: True)

    out_pkg = tmp_path / "perso.pkg"
    runner = CliRunner()
    # Record start.wav (Enter -> keep 'o'), then skip stop.wav ('s')
    res = runner.invoke(
        app,
        ["record", str(yaml_path), "--out", str(out_pkg), "--no-encrypt"],
        input="\no\ns\n",
    )
    assert res.exit_code == 0
    assert out_pkg.exists()
    with tarfile.open(out_pkg, "r:gz") as tar:
        assert sorted(tar.getnames()) == ["start.wav", "start_clean.wav"]


def test_tui_app_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VALETUDO_VOICING_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    state = AppState()
    assert state.script is None
    assert state.voice_name is None
    assert state.backend == "xtts"
    assert state.encrypt is True
    assert state.effect == "none"


def test_all_voice_effects(tmp_path: Path) -> None:
    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False, dtype="float32")
    tone = 0.3 * np.sin(2 * np.pi * 220 * t)
    src = tmp_path / "src.wav"
    sf.write(str(src), tone, sr, subtype="PCM_16")

    for fx in VOICE_EFFECTS:
        out = tmp_path / f"fx_{fx.id}.wav"
        apply_voice_effect(src, fx.id, output_wav=out)
        assert out.exists()
        info = sf.info(str(out))
        assert info.samplerate == 16000
        assert info.channels == 1

    with pytest.raises(ValueError):
        apply_voice_effect(src, "nonexistent_effect")


def test_cli_effects_list() -> None:
    runner = CliRunner()
    res = runner.invoke(app, ["effects"])
    assert res.exit_code == 0
    assert "vador" in res.output
    assert "r2d2" in res.output
    assert "kylo" in res.output


def test_script_name_and_jingles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = build_default_script(lang="fr", name="mon_robot")
    assert get_script_name(script) == "mon_robot"

    sr = 16000
    t = np.linspace(0, 0.5, sr // 2, endpoint=False, dtype="float32")
    src = tmp_path / "voice.wav"
    sf.write(str(src), 0.25 * np.sin(2 * np.pi * 220 * t), sr, subtype="PCM_16")

    for j in JINGLES:
        out = tmp_path / f"jg_{j.id}.wav"
        apply_jingle(src, j.id, output_wav=out)
        assert out.exists()

    monkeypatch.setattr("valetudo_voicing.cli.play_wav", lambda p: True)
    runner = CliRunner()
    assert runner.invoke(app, ["jingles"]).exit_code == 0
    assert runner.invoke(app, ["preview-effect", "vador", "--wav", str(src), "--jingle", "startrek"]).exit_code == 0


def test_apply_effect_from_base_pack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    base_dir = tmp_path / "recordings" / "mon_base"
    base_dir.mkdir(parents=True)

    sr = 16000
    t = np.linspace(0, 0.5, sr // 2, endpoint=False, dtype="float32")
    tone = 0.25 * np.sin(2 * np.pi * 220 * t)
    sf.write(str(base_dir / "start.wav"), tone, sr, subtype="PCM_16")
    sf.write(str(base_dir / "stop.wav"), tone, sr, subtype="PCM_16")

    runner = CliRunner()
    monkeypatch.setattr("valetudo_voicing.cli.play_wav", lambda p: True)
    res_prev = runner.invoke(app, ["preview-effect", "vador", "--base", "mon_base", "--jingle", "startrek"])
    assert res_prev.exit_code == 0

    out_pkg = tmp_path / "base_vador.pkg"
    res = runner.invoke(
        app,
        ["apply-effect", "mon_base", "--effect", "vador", "--jingle", "portal", "--out", str(out_pkg), "--no-encrypt"],
    )
    assert res.exit_code == 0
    assert out_pkg.exists()
    with tarfile.open(out_pkg, "r:gz") as tar:
        assert sorted(tar.getnames()) == ["start.wav", "start_clean.wav", "stop.wav", "stop_clean.wav"]


def test_i18n_en_fr() -> None:
    set_ui_lang("en")
    assert get_ui_lang() == "en"
    assert tr("Bonjour", "Hello") == "Hello"

    set_ui_lang("fr")
    assert get_ui_lang() == "fr"
    assert tr("Bonjour", "Hello") == "Bonjour"

    runner = CliRunner()
    res = runner.invoke(app, ["--ui-lang", "en", "effects"])
    assert res.exit_code == 0


def test_robots_and_ogg_packaging(tmp_path: Path) -> None:
    assert len(ROBOROCK_PROFILES) >= 10
    assert match_robot_model("Roborock S5 Max").id == "roborock_s5max"
    assert match_robot_model("roborock.vacuum.a15").id == "roborock_s7"
    assert match_robot_model("Q7 Max+").id == "roborock_q7max"

    wav_dir = tmp_path / "wavs"
    _create_dummy_wav(wav_dir / "start.wav")
    out_ogg = tmp_path / "ogg_pack.pkg"
    pkg_path, _ = build_pkg(wav_dir, out_ogg, encrypt=False, audio_format="ogg")
    with tarfile.open(pkg_path, "r:gz") as tar:
        assert sorted(tar.getnames()) == ["start.ogg", "start_clean.ogg"]

    runner = CliRunner()
    res = runner.invoke(app, ["robots"])
    assert res.exit_code == 0
    assert "roborock_s7" in res.output
