"""Full-screen ncurses TUI covering the complete ValetudoVoicing workflow."""

import curses
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
from typing import Any, Optional

from .deployer import deploy_to_valetudo
from .discovery import VoiceCandidate, search_character_voices
from .effects import EFFECT_MAP, VOICE_EFFECTS, apply_voice_effect
from .i18n import get_ui_lang, set_ui_lang, tr
from .jingles import JINGLE_MAP, JINGLES, apply_jingle, generate_jingle_audio
from .packager import build_pkg, compute_md5, normalize_wav_for_roborock
from .recorder import play_wav, trim_and_normalize_recording
from .robots import ROBOROCK_PROFILES, detect_robot_from_valetudo, get_robot_profile
from .sounds import build_default_script, get_script_name, load_script, save_script
from .tts import get_backend
from .voices import delete_voice_profile, list_voice_profiles, load_voice_profile, save_voice_profile
from .youtube import extract_soundboard_voice, extract_youtube_voice

CATEGORIES = ["all", "cleaning", "dock", "maintenance", "system", "error"]


@dataclass
class AppState:
    """Shared workflow state across TUI screens."""

    script_path: Optional[Path] = None
    script: Optional[dict[str, Any]] = None
    pack_name: str = "voicepack"
    robot_id: str = "roborock_s5"
    audio_format: str = "wav"
    voice_name: Optional[str] = None
    pkg_path: Optional[Path] = None
    pkg_md5: Optional[str] = None
    robot_ip: str = "192.168.1.50"
    lang: str = "fr"
    backend: str = "xtts"
    isolate_vocals: bool = False
    encrypt: bool = True
    device: str = "default"
    effect: str = "none"
    jingle: str = "none"
    keep_wavs: Optional[Path] = None
    port: int = 8765

    def __post_init__(self) -> None:
        for candidate in (Path("voicepack.fr.yaml"), Path("voicepack.yaml")):
            if candidate.exists():
                try:
                    self.script = load_script(candidate)
                    self.script_path = candidate
                    self.pack_name = get_script_name(self.script, candidate)
                    self.robot_id = str(self.script.get("robot", self.robot_id))
                    self.lang = str(self.script.get("language", self.lang))
                    self.keep_wavs = Path("recordings") / self.pack_name
                    break
                except Exception:
                    pass
        profiles = list_voice_profiles()
        if profiles and not self.voice_name:
            self.voice_name = profiles[0].name


def _init_colors() -> None:
    if not curses.has_colors():
        return
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_CYAN, -1)     # Header / accents
    curses.init_pair(2, curses.COLOR_GREEN, -1)    # OK / active
    curses.init_pair(3, curses.COLOR_YELLOW, -1)   # Warning / highlight
    curses.init_pair(4, curses.COLOR_RED, -1)      # Error / recording
    curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_CYAN)  # Selected row


def _safe_addstr(win: Any, y: int, x: int, text: str, attr: int = 0) -> None:
    max_y, max_x = win.getmaxyx()
    if y < 0 or y >= max_y or x >= max_x:
        return
    avail = max_x - x - 1
    if avail <= 0:
        return
    try:
        win.addnstr(y, x, text, avail, attr)
    except curses.error:
        pass


def _draw_header(stdscr: Any, state: AppState, subtitle: str) -> int:
    stdscr.erase()
    _, max_x = stdscr.getmaxyx()
    title = f" ValetudoVoicing — {subtitle} "
    _safe_addstr(stdscr, 0, 0, title.ljust(max_x - 1), curses.color_pair(5) | curses.A_BOLD)

    script_info = state.script_path.name if state.script_path else "Aucun"
    if state.script:
        active_n = sum(1 for v in state.script["sounds"].values() if v.get("enabled", True))
        script_info += f" ({active_n} sons)"
    voice_info = state.voice_name or "Aucune"
    pkg_info = state.pkg_path.name if state.pkg_path else "Aucun"

    status = f" Script: {script_info} | Robot: {state.robot_id} | Voix: {voice_info} | Pack: {pkg_info}"
    _safe_addstr(stdscr, 1, 0, status, curses.color_pair(1))
    _safe_addstr(stdscr, 2, 0, "─" * max(1, max_x - 1), curses.A_DIM)
    return 3


def _draw_footer(stdscr: Any, hints: str) -> None:
    max_y, max_x = stdscr.getmaxyx()
    _safe_addstr(stdscr, max_y - 2, 0, "─" * max(1, max_x - 1), curses.A_DIM)
    _safe_addstr(stdscr, max_y - 1, 0, f" {hints}", curses.color_pair(3))


def _show_message(stdscr: Any, state: AppState, title: str, lines: list[str], is_error: bool = False) -> None:
    y = _draw_header(stdscr, state, title)
    attr = curses.color_pair(4) if is_error else curses.color_pair(2)
    for idx, line in enumerate(lines):
        _safe_addstr(stdscr, y + 1 + idx, 2, line, attr if idx == 0 else 0)
    _draw_footer(stdscr, "Appuyez sur une touche pour continuer...")
    stdscr.refresh()
    stdscr.getch()


def _prompt_text(stdscr: Any, state: AppState, title: str, label: str, initial: str = "") -> Optional[str]:
    buf = list(initial)
    curses.curs_set(1)
    try:
        while True:
            y = _draw_header(stdscr, state, title)
            _safe_addstr(stdscr, y + 1, 2, label, curses.A_BOLD)
            _safe_addstr(stdscr, y + 3, 2, "> " + "".join(buf))
            _draw_footer(stdscr, "Entrée: Valider | Échap: Annuler")
            stdscr.move(y + 3, min(4 + len(buf), stdscr.getmaxyx()[1] - 2))
            stdscr.refresh()

            ch = stdscr.get_wch()
            if ch in ("\n", "\r", curses.KEY_ENTER):
                return "".join(buf).strip()
            if ch == "\x1b":
                return None
            if ch in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                if buf:
                    buf.pop()
            elif isinstance(ch, str) and ch.isprintable():
                buf.append(ch)
    finally:
        curses.curs_set(0)


def _confirm(stdscr: Any, state: AppState, question: str, default: bool = True) -> bool:
    y = _draw_header(stdscr, state, "Confirmation")
    suffix = " [O/n]" if default else " [o/N]"
    _safe_addstr(stdscr, y + 1, 2, question + suffix, curses.A_BOLD)
    _draw_footer(stdscr, "o: Oui | n: Non | Entrée: Défaut")
    stdscr.refresh()
    while True:
        ch = stdscr.getch()
        if ch in (ord("o"), ord("O"), ord("y"), ord("Y")):
            return True
        if ch in (ord("n"), ord("N")):
            return False
        if ch in (10, 13, curses.KEY_ENTER):
            return default


def _draw_progress(stdscr: Any, state: AppState, title: str, message: str, current: int = 0, total: int = 0) -> None:
    y = _draw_header(stdscr, state, title)
    _safe_addstr(stdscr, y + 1, 2, message, curses.color_pair(1) | curses.A_BOLD)
    if total > 0:
        width = min(50, max(10, stdscr.getmaxyx()[1] - 16))
        filled = int(width * current / total)
        bar = "█" * filled + "░" * (width - filled)
        pct = int(100 * current / total)
        _safe_addstr(stdscr, y + 3, 2, f"[{bar}] {current}/{total} ({pct}%)", curses.color_pair(2))
    _draw_footer(stdscr, "Opération en cours, veuillez patienter...")
    stdscr.refresh()


def _select_menu(
    stdscr: Any,
    state: AppState,
    title: str,
    items: list[str],
    footer: str = "↑/↓: Naviguer | Entrée: Sélectionner | q/Échap: Retour",
    initial_idx: int = 0,
) -> Optional[int]:
    idx = max(0, min(initial_idx, len(items) - 1))
    scroll = 0
    while True:
        y = _draw_header(stdscr, state, title)
        max_y, _ = stdscr.getmaxyx()
        visible_rows = max(1, max_y - y - 4)
        if idx < scroll:
            scroll = idx
        elif idx >= scroll + visible_rows:
            scroll = idx - visible_rows + 1

        for row_i in range(visible_rows):
            item_i = scroll + row_i
            if item_i >= len(items):
                break
            attr = curses.color_pair(5) | curses.A_BOLD if item_i == idx else 0
            prefix = "▶ " if item_i == idx else "  "
            _safe_addstr(stdscr, y + 1 + row_i, 2, f"{prefix}{items[item_i]}", attr)

        _draw_footer(stdscr, footer)
        stdscr.refresh()

        ch = stdscr.getch()
        if ch in (curses.KEY_UP, ord("k")):
            idx = (idx - 1) % len(items)
        elif ch in (curses.KEY_DOWN, ord("j")):
            idx = (idx + 1) % len(items)
        elif ch in (10, 13, curses.KEY_ENTER):
            return idx
        elif ch in (27, ord("q"), ord("Q")):
            return None


def _slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", text.strip().lower()).strip("_") or "voice"


def _pick_best_sample_wav(wavs: list[Path]) -> Path:
    """Pick a non-silent WAV sample (preferring start.wav / clean_finish.wav) for preview."""
    import numpy as np
    import soundfile as sf

    preferred = ["start.wav", "clean_finish.wav", "back_dock_failed.wav", "charging.wav"]
    ordered = sorted(
        wavs,
        key=lambda p: (preferred.index(p.name) if p.name in preferred else len(preferred), p.name),
    )
    for w in ordered:
        try:
            data, sr = sf.read(str(w), dtype="float32")
            if len(data) >= int(0.3 * sr) and float(np.max(np.abs(data))) > 0.01:
                return w
        except Exception:
            continue
    return ordered[0]


def _preview_current_effect(state: AppState, effect_id: str, sample_wav: Optional[Path] = None) -> None:
    """Play a quick audio preview of `effect_id` using `sample_wav`, active voice, or a test tone."""
    with tempfile.TemporaryDirectory(prefix="valetudo_tui_prev_") as tmp_dir:
        out_wav = Path(tmp_dir) / "preview.wav"
        src_wav: Optional[Path] = sample_wav
        if not src_wav and state.voice_name:
            try:
                src_wav = load_voice_profile(state.voice_name).reference_wav
            except Exception:
                src_wav = None

        if src_wav and src_wav.exists():
            normalize_wav_for_roborock(src_wav, out_wav)
        else:
            import numpy as np
            import soundfile as sf
            sr = 16000
            t = np.linspace(0, 1.0, sr, endpoint=False, dtype="float32")
            sf.write(str(out_wav), 0.35 * np.sin(2 * np.pi * 220 * t), sr, subtype="PCM_16")

        apply_voice_effect(out_wav, effect_id)
        if state.jingle != "none":
            apply_jingle(out_wav, state.jingle)
        if not play_wav(out_wav):
            raise RuntimeError("Aucun lecteur audio fonctionnel (pw-play, paplay, ffplay, aplay).")


def _pick_effect(stdscr: Any, state: AppState, preview_wav: Optional[Path] = None) -> None:
    items = [f"{fx.name:<24} — {fx.description}" for fx in VOICE_EFFECTS]
    idx = next((i for i, fx in enumerate(VOICE_EFFECTS) if fx.id == state.effect), 0)
    scroll = 0
    while True:
        y = _draw_header(stdscr, state, "Choisir un effet vocal")
        max_y, _ = stdscr.getmaxyx()
        visible = max(1, max_y - y - 4)
        if idx < scroll:
            scroll = idx
        elif idx >= scroll + visible:
            scroll = idx - visible + 1

        for row_i in range(visible):
            item_i = scroll + row_i
            if item_i >= len(items):
                break
            attr = curses.color_pair(5) | curses.A_BOLD if item_i == idx else 0
            prefix = "▶ " if item_i == idx else "  "
            _safe_addstr(stdscr, y + 1 + row_i, 2, f"{prefix}{items[item_i]}", attr)

        _draw_footer(stdscr, "↑/↓: Naviguer | Entrée: Sélectionner | p: Préécouter | q/Échap: Retour")
        stdscr.refresh()
        ch = stdscr.getch()
        if ch in (curses.KEY_UP, ord("k")):
            idx = (idx - 1) % len(items)
        elif ch in (curses.KEY_DOWN, ord("j")):
            idx = (idx + 1) % len(items)
        elif ch in (ord("p"), ord("P")):
            _draw_progress(stdscr, state, "Pré-écoute", f"Lecture de l'effet '{VOICE_EFFECTS[idx].name}'...")
            try:
                _preview_current_effect(state, VOICE_EFFECTS[idx].id, sample_wav=preview_wav)
            except Exception as exc:
                _show_message(stdscr, state, "Erreur de pré-écoute", [str(exc)], is_error=True)
        elif ch in (10, 13, curses.KEY_ENTER):
            state.effect = VOICE_EFFECTS[idx].id
            return
        elif ch in (27, ord("q"), ord("Q")):
            return


def _pick_robot(stdscr: Any, state: AppState) -> None:
    items = [f"Auto-détecter via Valetudo ({state.robot_ip})"]
    items.extend([f"{r.name:<34} [{', '.join(r.features)}]" for r in ROBOROCK_PROFILES])
    cur_idx = next((i + 1 for i, r in enumerate(ROBOROCK_PROFILES) if r.id == state.robot_id), 1)
    choice = _select_menu(stdscr, state, "Choisir le modèle Roborock", items, initial_idx=cur_idx)
    if choice is None:
        return
    if choice == 0:
        _draw_progress(stdscr, state, "Détection", f"Interrogation de Valetudo ({state.robot_ip})...")
        try:
            detected, raw_name = detect_robot_from_valetudo(state.robot_ip)
            if detected:
                state.robot_id = detected.id
                state.audio_format = detected.audio_format
                _show_message(stdscr, state, "Robot détecté", [f"{detected.name} ({raw_name})"])
            else:
                _show_message(stdscr, state, "Non reconnu", [f"Modèle renvoyé : {raw_name}"], is_error=True)
        except Exception as exc:
            _show_message(stdscr, state, "Erreur de détection", [str(exc)], is_error=True)
    else:
        prof = ROBOROCK_PROFILES[choice - 1]
        state.robot_id = prof.id
        state.audio_format = prof.audio_format


def _pick_jingle(stdscr: Any, state: AppState) -> None:
    items = [f"{j.name:<24} — {j.description}" for j in JINGLES]
    idx = next((i for i, j in enumerate(JINGLES) if j.id == state.jingle), 0)
    while True:
        y = _draw_header(stdscr, state, "Choisir un jingle d'intro")
        for i, line in enumerate(items):
            attr = curses.color_pair(5) | curses.A_BOLD if i == idx else 0
            prefix = "▶ " if i == idx else "  "
            _safe_addstr(stdscr, y + 1 + i, 2, f"{prefix}{line}", attr)
        _draw_footer(stdscr, "↑/↓: Naviguer | Entrée: Sélectionner | p: Préécouter | q/Échap: Retour")
        stdscr.refresh()
        ch = stdscr.getch()
        if ch in (curses.KEY_UP, ord("k")):
            idx = (idx - 1) % len(items)
        elif ch in (curses.KEY_DOWN, ord("j")):
            idx = (idx + 1) % len(items)
        elif ch in (ord("p"), ord("P")):
            import soundfile as sf
            with tempfile.TemporaryDirectory(prefix="valetudo_jingle_") as tmp_dir:
                jw = Path(tmp_dir) / "jingle.wav"
                sf.write(str(jw), generate_jingle_audio(JINGLES[idx].id, 16000), 16000, subtype="PCM_16")
                play_wav(jw)
        elif ch in (10, 13, curses.KEY_ENTER):
            state.jingle = JINGLES[idx].id
            return
        elif ch in (27, ord("q"), ord("Q")):
            return


def _screen_learn(stdscr: Any, state: AppState) -> None:
    choice = _select_menu(
        stdscr,
        state,
        "1. Apprendre une voix",
        [
            "Recherche automatique par nom de personnage (YouTube + 101soundboards)",
            "Depuis une URL YouTube directe (avec découpe optionnelle)",
            f"Option isolation vocale Demucs : {'OUI' if state.isolate_vocals else 'NON'} (Entrée pour inverser)",
        ],
    )
    if choice is None:
        return
    if choice == 2:
        state.isolate_vocals = not state.isolate_vocals
        _screen_learn(stdscr, state)
        return

    if choice == 0:
        character = _prompt_text(stdscr, state, "Apprendre par personnage", "Nom du personnage (ex: GLaDOS, Dark Vador) :")
        if not character:
            return
        lang = _prompt_text(stdscr, state, "Apprendre par personnage", "Langue recherchée (fr, en, es, de, it, ja...) :", state.lang)
        if not lang:
            return
        name = _prompt_text(stdscr, state, "Apprendre par personnage", "Nom du profil vocal :", _slugify(character))
        if not name:
            return

        _draw_progress(stdscr, state, "Recherche", f"Recherche d'extraits pour '{character}' ({lang})...")
        try:
            candidates = search_character_voices(character=character, lang=lang, limit=5)
        except Exception as exc:
            _show_message(stdscr, state, "Erreur de recherche", [str(exc)], is_error=True)
            return

        if not candidates:
            _show_message(stdscr, state, "Aucun résultat", [f"Aucun extrait trouvé pour '{character}' ({lang})."], is_error=True)
            return

        labels = [
            f"[{c.source}] {c.title} ({int(c.duration_sec)}s)" if c.duration_sec else f"[{c.source}] {c.title}"
            for c in candidates
        ]
        pick = _select_menu(stdscr, state, "Choisir l'extrait vocal", labels)
        if pick is None:
            return
        cand: VoiceCandidate = candidates[pick]

        _draw_progress(stdscr, state, "Extraction", f"Téléchargement et extraction de '{cand.title}'...")
        try:
            if cand.source == "101soundboards" and cand.audio_urls:
                tmp_dir, wav_path, dur = extract_soundboard_voice(cand.audio_urls, isolate_vocals=state.isolate_vocals)
            else:
                tmp_dir, wav_path, dur = extract_youtube_voice(
                    cand.url, isolate_vocals=state.isolate_vocals, auto_trim=True
                )
            try:
                profile = save_voice_profile(name, wav_path, cand.url, lang, state.isolate_vocals, dur)
            finally:
                tmp_dir.cleanup()
            state.voice_name = profile.name
            _show_message(stdscr, state, "Voix apprise", [f"Profil '{profile.name}' enregistré ({profile.duration_sec:.1f}s) !"])
        except Exception as exc:
            _show_message(stdscr, state, "Erreur d'extraction", [str(exc)], is_error=True)

    elif choice == 1:
        url = _prompt_text(stdscr, state, "Apprendre depuis YouTube", "URL de la vidéo YouTube :")
        if not url:
            return
        name = _prompt_text(stdscr, state, "Apprendre depuis YouTube", "Nom du profil vocal :", "ma_voix")
        if not name:
            return
        start = _prompt_text(stdscr, state, "Découpe optionnelle", "Début (ex: 00:00:15, laisser vide si aucun) :", "")
        if start is None:
            return
        end = _prompt_text(stdscr, state, "Découpe optionnelle", "Fin (ex: 00:00:45, laisser vide si aucun) :", "")
        if end is None:
            return
        lang = _prompt_text(stdscr, state, "Langue source", "Langue de la vidéo (fr, en, auto...) :", state.lang) or "auto"

        _draw_progress(stdscr, state, "Extraction YouTube", f"Téléchargement de {url}...")
        try:
            tmp_dir, wav_path, dur = extract_youtube_voice(
                url=url,
                start=start or None,
                end=end or None,
                isolate_vocals=state.isolate_vocals,
            )
            try:
                profile = save_voice_profile(name, wav_path, url, lang, state.isolate_vocals, dur)
            finally:
                tmp_dir.cleanup()
            state.voice_name = profile.name
            _show_message(stdscr, state, "Voix apprise", [f"Profil '{profile.name}' enregistré ({profile.duration_sec:.1f}s) !"])
        except Exception as exc:
            _show_message(stdscr, state, "Erreur YouTube", [str(exc)], is_error=True)


def _screen_voices(stdscr: Any, state: AppState) -> None:
    idx = 0
    while True:
        profiles = list_voice_profiles()
        if not profiles:
            _show_message(stdscr, state, "Profils vocaux", ["Aucun profil vocal enregistré.", "Utilisez '1. Apprendre une voix'."])
            return

        idx = min(idx, len(profiles) - 1)
        y = _draw_header(stdscr, state, "2. Profils vocaux enregistrés")
        for i, p in enumerate(profiles):
            active_mark = "* " if p.name == state.voice_name else "  "
            demucs_tag = " [Demucs]" if p.isolated_vocals else ""
            line = f"{active_mark}{p.name} ({p.source_lang}, {p.duration_sec:.1f}s){demucs_tag} — {p.source_url}"
            attr = curses.color_pair(5) | curses.A_BOLD if i == idx else (curses.color_pair(2) if p.name == state.voice_name else 0)
            _safe_addstr(stdscr, y + 1 + i, 2, line, attr)

        _draw_footer(stdscr, "Entrée: Sélectionner | e: Écouter | d: Supprimer | q/Échap: Retour")
        stdscr.refresh()
        ch = stdscr.getch()
        if ch in (curses.KEY_UP, ord("k")):
            idx = (idx - 1) % len(profiles)
        elif ch in (curses.KEY_DOWN, ord("j")):
            idx = (idx + 1) % len(profiles)
        elif ch in (10, 13, curses.KEY_ENTER):
            state.voice_name = profiles[idx].name
            _show_message(stdscr, state, "Voix sélectionnée", [f"Voix active : {state.voice_name}"])
            return
        elif ch in (ord("e"), ord("E")):
            play_wav(profiles[idx].reference_wav)
        elif ch in (ord("d"), ord("D"), curses.KEY_DC):
            target = profiles[idx].name
            if _confirm(stdscr, state, f"Supprimer définitivement le profil '{target}' ?", default=False):
                delete_voice_profile(target)
                if state.voice_name == target:
                    state.voice_name = None
        elif ch in (27, ord("q"), ord("Q")):
            return


def _screen_script_editor(stdscr: Any, state: AppState) -> None:
    if not state.script or not state.script_path:
        return
    cat_idx = 0
    idx = 0
    scroll = 0

    while True:
        current_cat = CATEGORIES[cat_idx]
        entries = [
            (fname, entry)
            for fname, entry in state.script["sounds"].items()
            if current_cat == "all" or entry.get("category") == current_cat
        ]
        if not entries:
            cat_idx = 0
            continue
        idx = min(idx, len(entries) - 1)

        y = _draw_header(stdscr, state, f"3. Éditeur de textes [{state.script_path.name}] (Filtre: {current_cat})")
        max_y, _ = stdscr.getmaxyx()
        visible = max(1, max_y - y - 4)
        if idx < scroll:
            scroll = idx
        elif idx >= scroll + visible:
            scroll = idx - visible + 1

        for row_i in range(visible):
            item_i = scroll + row_i
            if item_i >= len(entries):
                break
            fname, entry = entries[item_i]
            flag = "[✓]" if entry.get("enabled", True) else "[ ]"
            text = str(entry.get("text", ""))
            line = f"{flag} {fname:<18} | {text}"
            attr = curses.color_pair(5) | curses.A_BOLD if item_i == idx else (0 if entry.get("enabled", True) else curses.A_DIM)
            _safe_addstr(stdscr, y + 1 + row_i, 2, line, attr)

        _draw_footer(stdscr, "↑/↓: Naviguer | Entrée: Éditer texte | Espace: Activer/Désactiver | c: Catégorie | s: Sauvegarder | q: Retour")
        stdscr.refresh()
        ch = stdscr.getch()

        if ch in (curses.KEY_UP, ord("k")):
            idx = (idx - 1) % len(entries)
        elif ch in (curses.KEY_DOWN, ord("j")):
            idx = (idx + 1) % len(entries)
        elif ch == ord(" "):
            fname, entry = entries[idx]
            entry["enabled"] = not entry.get("enabled", True)
        elif ch in (ord("c"), ord("C")):
            cat_idx = (cat_idx + 1) % len(CATEGORIES)
            idx = 0
            scroll = 0
        elif ch in (10, 13, curses.KEY_ENTER):
            fname, entry = entries[idx]
            new_text = _prompt_text(
                stdscr,
                state,
                f"Édition de {fname}",
                f"{entry.get('description', '')} :",
                str(entry.get("text", "")),
            )
            if new_text is not None:
                entry["text"] = new_text
                entry["enabled"] = bool(new_text.strip())
        elif ch in (ord("s"), ord("S")):
            save_script(state.script, state.script_path)
            _show_message(stdscr, state, "Sauvegardé", [f"Script enregistré dans {state.script_path}"])
        elif ch in (27, ord("q"), ord("Q")):
            save_script(state.script, state.script_path)
            return


def _screen_script(stdscr: Any, state: AppState) -> None:
    while True:
        items = [
            "Créer un nouveau script YAML par défaut (fr)",
            "Créer un nouveau script YAML par défaut (en)",
            "Charger un fichier YAML existant",
        ]
        if state.script and state.script_path:
            items.insert(0, f"Éditer le script actif ({state.script_path.name})")

        choice = _select_menu(stdscr, state, "3. Script & Textes du voicepack", items)
        if choice is None:
            return

        has_active = bool(state.script and state.script_path)
        if has_active and choice == 0:
            _screen_script_editor(stdscr, state)
            continue

        offset = 1 if has_active else 0
        if choice in (offset, offset + 1):
            lang = "fr" if choice == offset else "en"
            _pick_robot(stdscr, state)
            pack_name = _prompt_text(stdscr, state, "Nouveau voicepack", "Nom du voicepack (servira à nommer le .pkg) :", "mon_voicepack")
            if not pack_name:
                continue
            clean_name = _slugify(pack_name)
            path_str = _prompt_text(stdscr, state, "Nouveau script", "Chemin du fichier YAML à créer :", f"{clean_name}.yaml")
            if not path_str:
                continue
            target = Path(path_str)
            if target.exists() and not _confirm(stdscr, state, f"{target} existe déjà. L'écraser ?", default=False):
                continue
            state.pack_name = clean_name
            state.script = build_default_script(lang=lang, name=clean_name, robot=state.robot_id)
            state.script_path = target
            state.lang = lang
            state.keep_wavs = Path("recordings") / clean_name
            save_script(state.script, state.script_path)
            _screen_script_editor(stdscr, state)
        elif choice == offset + 2:
            path_str = _prompt_text(stdscr, state, "Charger un script", "Chemin du fichier YAML :", "voicepack.fr.yaml")
            if not path_str:
                continue
            target = Path(path_str)
            try:
                state.script = load_script(target)
                state.script_path = target
                state.pack_name = get_script_name(state.script, target)
                state.lang = str(state.script.get("language", state.lang))
                state.keep_wavs = Path("recordings") / state.pack_name
                _screen_script_editor(stdscr, state)
            except Exception as exc:
                _show_message(stdscr, state, "Erreur de chargement", [str(exc)], is_error=True)


def _screen_generate(stdscr: Any, state: AppState) -> None:
    if not state.script or not state.script_path:
        _show_message(stdscr, state, "Script manquant", ["Chargez ou créez d'abord un script YAML (Menu 3)."], is_error=True)
        return
    if not state.voice_name:
        _show_message(stdscr, state, "Voix manquante", ["Apprenez ou sélectionnez d'abord une voix (Menu 1 ou 2)."], is_error=True)
        return

    out_path = Path(f"{state.pack_name}.pkg")
    while True:
        fx_name = EFFECT_MAP.get(state.effect, VOICE_EFFECTS[0]).name
        jg_name = JINGLE_MAP.get(state.jingle, JINGLES[0]).name
        items = [
            f"Voix active       : {state.voice_name}",
            f"Moteur TTS        : {state.backend} (Entrée pour changer)",
            f"Langue cible      : {state.lang}",
            f"Effet vocal       : {fx_name}",
            f"Jingle d'intro    : {jg_name}",
            f"Fichier .pkg      : {out_path}",
            f"Dossier keep-wavs : {state.keep_wavs or 'Aucun (temporaire)'}",
            f"Chiffrement ccrypt: {'OUI' if state.encrypt else 'NON (.tar.gz)'}",
            "▶ LANCER LA GÉNÉRATION DU VOICEPACK",
        ]
        choice = _select_menu(stdscr, state, "4. Générer par synthèse vocale (TTS)", items)
        if choice is None:
            return
        if choice == 0:
            _screen_voices(stdscr, state)
        elif choice == 1:
            state.backend = "chatterbox" if state.backend == "xtts" else "xtts"
        elif choice == 2:
            val = _prompt_text(stdscr, state, "Langue cible", "Code langue (fr, en, es, de, it, ja...) :", state.lang)
            if val:
                state.lang = val
        elif choice == 3:
            _pick_effect(stdscr, state)
        elif choice == 4:
            _pick_jingle(stdscr, state)
        elif choice == 5:
            val = _prompt_text(stdscr, state, "Fichier de sortie", "Chemin du .pkg :", str(out_path))
            if val:
                out_path = Path(val)
        elif choice == 6:
            val = _prompt_text(stdscr, state, "Conserver les WAV", "Dossier (vide = temporaire) :", str(state.keep_wavs or ""))
            if val is not None:
                state.keep_wavs = Path(val) if val else None
        elif choice == 7:
            state.encrypt = not state.encrypt
        elif choice == 8:
            break

    enabled_items = [
        (fname, entry)
        for fname, entry in state.script["sounds"].items()
        if entry.get("enabled", True) and str(entry.get("text", "")).strip()
    ]
    if not enabled_items:
        _show_message(stdscr, state, "Aucun son", ["Aucun son actif dans le script."], is_error=True)
        return

    try:
        profile = load_voice_profile(state.voice_name)
        tts = get_backend(state.backend)
        _draw_progress(stdscr, state, "Synthèse TTS", f"Chargement du modèle {tts.name} sur CPU...")
        tts.load()

        with tempfile.TemporaryDirectory(prefix="valetudo_tui_gen_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            raw_dir = tmp_path / "raw"
            norm_dir = state.keep_wavs if state.keep_wavs else (tmp_path / "wavs")
            raw_dir.mkdir(parents=True, exist_ok=True)
            norm_dir.mkdir(parents=True, exist_ok=True)

            total = len(enabled_items)
            for idx, (fname, entry) in enumerate(enabled_items, start=1):
                _draw_progress(stdscr, state, "Synthèse TTS", f"Synthèse de {fname}...", idx - 1, total)
                raw_wav = raw_dir / fname
                norm_wav = norm_dir / fname
                tts.synthesize(str(entry["text"]).strip(), profile.reference_wav, state.lang, raw_wav)
                normalize_wav_for_roborock(raw_wav, norm_wav)
                if state.effect != "none":
                    apply_voice_effect(norm_wav, state.effect)
                if state.jingle != "none":
                    apply_jingle(norm_wav, state.jingle)

            _draw_progress(stdscr, state, "Empaquetage", f"Création de {out_path}...", total, total)
            pkg_path, md5_hex = build_pkg(norm_dir, out_path, encrypt=state.encrypt, audio_format=state.audio_format)

        state.pkg_path = pkg_path
        state.pkg_md5 = md5_hex
        _show_message(
            stdscr,
            state,
            "Voicepack généré",
            [
                f"Fichier : {pkg_path}",
                f"Sons inclus : {len(enabled_items)} | Langue : {state.lang}",
                f"MD5 : {md5_hex}",
            ],
        )
    except Exception as exc:
        _show_message(stdscr, state, "Erreur de génération", [str(exc)], is_error=True)


def _record_curses_until_enter(stdscr: Any, state: AppState, fname: str, phrase: str, output_wav: Path) -> float:
    arecord = shutil.which("arecord")
    if not arecord:
        raise RuntimeError("Le binaire 'arecord' (alsa-utils) est requis pour enregistrer au microphone.")

    output_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        arecord, "-D", state.device, "-f", "S16_LE", "-r", "24000", "-c", "1", "-t", "wav", "-q", str(output_wav)
    ]
    start_time = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        y = _draw_header(stdscr, state, "5. Dictée vocale — Enregistrement")
        _safe_addstr(stdscr, y + 1, 2, f"Son : {fname}", curses.A_BOLD)
        _safe_addstr(stdscr, y + 3, 2, f"« {phrase} »", curses.color_pair(3) | curses.A_BOLD)
        _safe_addstr(stdscr, y + 5, 2, "🎙️  ENREGISTREMENT EN COURS...", curses.color_pair(4) | curses.A_BOLD)
        _draw_footer(stdscr, "Appuyez sur Entrée pour arrêter l'enregistrement")
        stdscr.refresh()
        while True:
            ch = stdscr.getch()
            if ch in (10, 13, curses.KEY_ENTER):
                break
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    return max(0.0, time.monotonic() - start_time)


def _draw_rec_progress_bar(stdscr: Any, y: int, done_count: int, total: int) -> None:
    width = min(40, max(10, stdscr.getmaxyx()[1] - 28))
    filled = int(width * done_count / total) if total else 0
    bar = "█" * filled + "░" * (width - filled)
    pct = int(100 * done_count / total) if total else 0
    _safe_addstr(stdscr, y, 2, f"Progression : [{bar}] {done_count}/{total} ({pct}%)", curses.color_pair(2) | curses.A_BOLD)


def _screen_record(stdscr: Any, state: AppState) -> None:
    if not state.script or not state.script_path:
        _show_message(stdscr, state, "Script manquant", ["Chargez ou créez d'abord un script YAML (Menu 3)."], is_error=True)
        return

    out_path = Path(f"{state.pack_name}.pkg")
    if not state.keep_wavs:
        state.keep_wavs = Path("recordings") / state.pack_name
    cat_filter = "all"
    while True:
        fx_name = EFFECT_MAP.get(state.effect, VOICE_EFFECTS[0]).name
        jg_name = JINGLE_MAP.get(state.jingle, JINGLES[0]).name
        items = [
            f"Catégorie         : {cat_filter}",
            f"Effet vocal       : {fx_name}",
            f"Jingle d'intro    : {jg_name}",
            f"Périphérique ALSA : {state.device}",
            f"Dossier keep-wavs : {state.keep_wavs}",
            f"Fichier .pkg      : {out_path}",
            f"Chiffrement ccrypt: {'OUI' if state.encrypt else 'NON (.tar.gz)'}",
            "▶ DÉMARRER LA DICTÉE INTERACTIVE",
        ]
        choice = _select_menu(stdscr, state, "5. Dicter avec ma propre voix", items)
        if choice is None:
            return
        if choice == 0:
            cat_filter = CATEGORIES[(CATEGORIES.index(cat_filter) + 1) % len(CATEGORIES)]
        elif choice == 1:
            _pick_effect(stdscr, state)
        elif choice == 2:
            _pick_jingle(stdscr, state)
        elif choice == 3:
            val = _prompt_text(stdscr, state, "Périphérique ALSA", "Device (ex: default, hw:0,0) :", state.device)
            if val:
                state.device = val
        elif choice == 4:
            val = _prompt_text(stdscr, state, "Dossier keep-wavs", "Dossier pour reprendre plus tard :", str(state.keep_wavs or ""))
            if val is not None:
                state.keep_wavs = Path(val) if val else None
        elif choice == 5:
            val = _prompt_text(stdscr, state, "Fichier de sortie", "Chemin du .pkg :", str(out_path))
            if val:
                out_path = Path(val)
        elif choice == 6:
            state.encrypt = not state.encrypt
        elif choice == 7:
            break

    items_to_rec = [
        (fname, entry)
        for fname, entry in state.script["sounds"].items()
        if entry.get("enabled", True) and (cat_filter == "all" or entry.get("category") == cat_filter)
    ]
    if not items_to_rec:
        _show_message(stdscr, state, "Aucun son", ["Aucun son actif pour cette catégorie."], is_error=True)
        return

    try:
        with tempfile.TemporaryDirectory(prefix="valetudo_tui_rec_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            raw_dir = tmp_path / "raw"
            staged_dir = tmp_path / "staged"
            norm_dir = state.keep_wavs if state.keep_wavs else (tmp_path / "wavs")
            raw_dir.mkdir(parents=True, exist_ok=True)
            staged_dir.mkdir(parents=True, exist_ok=True)
            norm_dir.mkdir(parents=True, exist_ok=True)

            quit_early = False
            for idx, (fname, entry) in enumerate(items_to_rec, start=1):
                if quit_early:
                    break
                norm_wav = norm_dir / fname
                raw_wav = raw_dir / fname
                staged_wav = staged_dir / fname
                desc = entry.get("description", "")
                text = str(entry.get("text", "")).strip()

                while True:
                    done_count = sum(1 for f, _ in items_to_rec if (norm_dir / f).exists())
                    y = _draw_header(stdscr, state, f"5. Dictée ({idx}/{len(items_to_rec)})")
                    _draw_rec_progress_bar(stdscr, y + 1, done_count, len(items_to_rec))
                    _safe_addstr(stdscr, y + 3, 2, f"{fname} — {desc}", curses.A_BOLD)
                    _safe_addstr(stdscr, y + 5, 2, f"Phrase : « {text} »", curses.color_pair(3) | curses.A_BOLD)
                    if norm_wav.exists():
                        _safe_addstr(stdscr, y + 7, 2, "(Déjà enregistré — Entrée pour remplacer, 's' pour conserver)", curses.color_pair(2))
                    _draw_footer(stdscr, "Entrée: Enregistrer | s: Passer/Conserver | q: Terminer & empaqueter")
                    stdscr.refresh()

                    ch = stdscr.getch()
                    if ch in (ord("q"), ord("Q"), 27):
                        quit_early = True
                        break
                    if ch in (ord("s"), ord("S")):
                        break
                    if ch not in (10, 13, curses.KEY_ENTER):
                        continue

                    dur = _record_curses_until_enter(stdscr, state, fname, text, raw_wav)
                    trim_and_normalize_recording(raw_wav, norm_wav)
                    apply_voice_effect(norm_wav, state.effect, output_wav=staged_wav)
                    if state.jingle != "none":
                        apply_jingle(staged_wav, state.jingle)
                    play_wav(staged_wav)

                    while True:
                        done_count = sum(1 for f, _ in items_to_rec if (norm_dir / f).exists())
                        y2 = _draw_header(stdscr, state, f"5. Validation ({idx}/{len(items_to_rec)})")
                        _draw_rec_progress_bar(stdscr, y2 + 1, done_count, len(items_to_rec))
                        _safe_addstr(stdscr, y2 + 3, 2, f"{fname} enregistré ({dur:.1f}s)", curses.color_pair(2) | curses.A_BOLD)
                        _safe_addstr(stdscr, y2 + 5, 2, f"« {text} »")
                        _draw_footer(stdscr, "o/Entrée: Garder | r: Ré-enregistrer | e: Réécouter | s: Passer | q: Terminer")
                        stdscr.refresh()
                        post = stdscr.getch()
                        if post in (ord("e"), ord("E")):
                            play_wav(staged_wav)
                        elif post in (ord("r"), ord("R")):
                            break
                        elif post in (ord("s"), ord("S")):
                            if norm_wav.exists():
                                norm_wav.unlink()
                            if staged_wav.exists():
                                staged_wav.unlink()
                            post = -99
                            break
                        elif post in (ord("q"), ord("Q")):
                            quit_early = True
                            post = -98
                            break
                        elif post in (ord("o"), ord("O"), 10, 13, curses.KEY_ENTER):
                            post = -98
                            break
                    if post in (-98, -99):
                        break

            base_wavs = sorted(norm_dir.glob("*.wav"))
            if not base_wavs:
                _show_message(stdscr, state, "Annulé", ["Aucun son enregistré."])
                return

            for i, bw in enumerate(base_wavs, start=1):
                sw = staged_dir / bw.name
                if not sw.exists():
                    _draw_progress(stdscr, state, "Effets & Empaquetage", f"Traitement de {bw.name}...", i - 1, len(base_wavs))
                    apply_voice_effect(bw, state.effect, output_wav=sw)
                    if state.jingle != "none":
                        apply_jingle(sw, state.jingle)

            _draw_progress(stdscr, state, "Empaquetage", f"Création de {out_path}...")
            pkg_path, md5_hex = build_pkg(staged_dir, out_path, encrypt=state.encrypt, audio_format=state.audio_format)
            state.pkg_path = pkg_path
            state.pkg_md5 = md5_hex
            _show_message(
                stdscr,
                state,
                "Voicepack personnel prêt",
                [
                    f"Fichier : {pkg_path}",
                    f"Base propre conservée : {norm_dir}",
                    f"Sons inclus : {len(base_wavs)} | MD5 : {md5_hex}",
                ],
            )
    except Exception as exc:
        _show_message(stdscr, state, "Erreur de dictée", [str(exc)], is_error=True)


def _screen_apply_base(stdscr: Any, state: AppState) -> None:
    rec_root = Path("recordings")
    base_dirs = sorted([d for d in rec_root.iterdir() if d.is_dir() and list(d.glob("*.wav"))]) if rec_root.is_dir() else []

    menu_opts = [f"{d.name} ({len(list(d.glob('*.wav')))} sons) — {d}" for d in base_dirs]
    menu_opts.append("Autre dossier de fichiers .wav...")
    pick = _select_menu(stdscr, state, "6. Choisir un pack d'enregistrements de base", menu_opts)
    if pick is None:
        return

    if pick < len(base_dirs):
        src_dir = base_dirs[pick]
    else:
        val = _prompt_text(stdscr, state, "Dossier source", "Chemin du dossier contenant les .wav :", str(state.keep_wavs or ""))
        if not val:
            return
        src_dir = Path(val)
        if not src_dir.is_dir() or not list(src_dir.glob("*.wav")):
            _show_message(stdscr, state, "Introuvable", [f"Aucun .wav trouvé dans {src_dir}"], is_error=True)
            return

    wavs = sorted(src_dir.glob("*.wav"))
    sample_wav = _pick_best_sample_wav(wavs)
    out_path = Path(f"{src_dir.name}_{state.effect}.pkg")
    while True:
        fx_name = EFFECT_MAP.get(state.effect, VOICE_EFFECTS[0]).name
        jg_name = JINGLE_MAP.get(state.jingle, JINGLES[0]).name
        items = [
            f"Pack de base      : {src_dir}",
            f"Effet vocal       : {fx_name}",
            f"Jingle d'intro    : {jg_name}",
            f"Fichier .pkg      : {out_path}",
            f"Format audio      : {state.audio_format} (Entrée pour changer)",
            f"Chiffrement ccrypt: {'OUI' if state.encrypt else 'NON (.tar.gz)'}",
            f"🔊 Préécouter un extrait ({sample_wav.name}) avec cet effet",
            "▶ GÉNÉRER LE .PKG AVEC EFFET",
        ]
        choice = _select_menu(stdscr, state, "6. Appliquer effet/jingle sur pack de base", items)
        if choice is None:
            return
        if choice == 1:
            _pick_effect(stdscr, state, preview_wav=sample_wav)
            out_path = Path(f"{src_dir.name}_{state.effect}.pkg")
        elif choice == 2:
            _pick_jingle(stdscr, state)
        elif choice == 3:
            val = _prompt_text(stdscr, state, "Fichier de sortie", "Chemin du .pkg :", str(out_path))
            if val:
                out_path = Path(val)
        elif choice == 4:
            state.audio_format = "ogg" if state.audio_format == "wav" else "wav"
        elif choice == 5:
            state.encrypt = not state.encrypt
        elif choice == 6:
            _draw_progress(stdscr, state, "Aperçu", f"Lecture de {sample_wav.name} (effet: {state.effect}, jingle: {state.jingle})...")
            try:
                _preview_current_effect(state, state.effect, sample_wav=sample_wav)
            except Exception as exc:
                _show_message(stdscr, state, "Erreur de pré-écoute", [str(exc)], is_error=True)
        elif choice == 7:
            break
    try:
        with tempfile.TemporaryDirectory(prefix="valetudo_tui_fx_") as tmp_dir:
            staged_dir = Path(tmp_dir)
            for idx, w in enumerate(wavs, start=1):
                _draw_progress(stdscr, state, "Traitement audio", f"Application sur {w.name}...", idx - 1, len(wavs))
                dst = staged_dir / w.name
                apply_voice_effect(w, state.effect, output_wav=dst)
                if state.jingle != "none":
                    apply_jingle(dst, state.jingle)

            _draw_progress(stdscr, state, "Empaquetage", f"Création de {out_path}...", len(wavs), len(wavs))
            pkg_path, md5_hex = build_pkg(staged_dir, out_path, encrypt=state.encrypt, audio_format=state.audio_format)
            state.pkg_path = pkg_path
            state.pkg_md5 = md5_hex
            _show_message(
                stdscr,
                state,
                "Pack généré",
                [f"Fichier : {pkg_path}", f"Sons traités : {len(wavs)} | Effet : {state.effect}", f"MD5 : {md5_hex}"],
            )
    except Exception as exc:
        _show_message(stdscr, state, "Erreur", [str(exc)], is_error=True)


def _screen_deploy(stdscr: Any, state: AppState) -> None:
    while True:
        pkg_label = str(state.pkg_path) if state.pkg_path else "Aucun (sélectionner un fichier)"
        items = [
            f"Fichier .pkg  : {pkg_label}",
            f"IP du robot   : {state.robot_ip}",
            f"Modèle        : {state.robot_id} (Entrée pour changer / auto-détecter)",
            f"Code langue   : {state.lang}",
            f"Port HTTP     : {state.port}",
            "▶ ENVOYER SUR LE ROBOROCK (VALETUDO)",
        ]
        choice = _select_menu(stdscr, state, "7. Déployer sur le Roborock (Valetudo)", items)
        if choice is None:
            return
        if choice == 0:
            val = _prompt_text(stdscr, state, "Fichier .pkg", "Chemin du fichier .pkg :", str(state.pkg_path or "voicepack.pkg"))
            if val:
                p = Path(val)
                if p.exists():
                    state.pkg_path = p
                    state.pkg_md5 = compute_md5(p)
                else:
                    _show_message(stdscr, state, "Introuvable", [f"Le fichier {p} n'existe pas."], is_error=True)
        elif choice == 1:
            val = _prompt_text(stdscr, state, "IP du robot", "Adresse IP locale Valetudo :", state.robot_ip)
            if val:
                state.robot_ip = val
        elif choice == 2:
            _pick_robot(stdscr, state)
        elif choice == 3:
            val = _prompt_text(stdscr, state, "Langue Valetudo", "Code langue (fr, en...) :", state.lang)
            if val:
                state.lang = val
        elif choice == 4:
            val = _prompt_text(stdscr, state, "Port HTTP local", "Port (ex: 8765) :", str(state.port))
            if val and val.isdigit():
                state.port = int(val)
        elif choice == 5:
            if not state.pkg_path or not state.pkg_path.exists():
                _show_message(stdscr, state, "Pack manquant", ["Sélectionnez ou générez d'abord un fichier .pkg."], is_error=True)
                continue
            _draw_progress(stdscr, state, "Déploiement", f"Envoi de {state.pkg_path.name} vers {state.robot_ip}...")
            try:
                res = deploy_to_valetudo(state.pkg_path, state.robot_ip, language=state.lang, port=state.port)
                msg = (
                    "Le robot a téléchargé le voicepack !"
                    if res["downloaded"]
                    else "Requête envoyée, mais téléchargement non confirmé dans le délai."
                )
                _show_message(stdscr, state, "Déploiement terminé", [msg, f"URL : {res['url']}", f"MD5 : {res['md5']}"])
                return
            except Exception as exc:
                _show_message(stdscr, state, "Erreur de déploiement", [str(exc)], is_error=True)


def _tui_main(stdscr: Any) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    _init_colors()
    state = AppState()

    idx = 0
    while True:
        ui = get_ui_lang().upper()
        menu_items = [
            tr("1. Apprendre une voix (Personnage auto ou URL YouTube)", "1. Learn a voice (Character search or YouTube URL)"),
            tr("2. Gérer les profils vocaux enregistrés", "2. Manage saved voice profiles"),
            tr("3. Créer / Éditer le script YAML et les textes", "3. Create / Edit YAML script & phrases"),
            tr("4. Générer le .pkg par synthèse vocale (TTS)", "4. Generate .pkg via TTS voice cloning"),
            tr("5. Dicter le .pkg avec ma propre voix (Microphone)", "5. Record .pkg with your own voice (Microphone)"),
            tr("6. Appliquer effet/jingle sur un pack de base (sans réenregistrer)", "6. Apply effect/jingle to an existing base pack"),
            tr("7. Déployer le .pkg sur le Roborock S5 (Valetudo)", "7. Deploy .pkg to Roborock S5 (Valetudo)"),
            tr(f"Langue interface : {ui} (Entrée pour changer)", f"UI Language: {ui} (Enter to switch)"),
            tr("Quitter", "Quit"),
        ]
        choice = _select_menu(
            stdscr,
            state,
            tr("Menu principal (Workflow complet)", "Main Menu (Full Workflow)"),
            menu_items,
            footer=tr("↑/↓: Naviguer | Entrée: Ouvrir | q: Quitter", "↑/↓: Navigate | Enter: Open | q: Quit"),
            initial_idx=idx,
        )
        if choice is None or choice == 8:
            return
        idx = choice
        if choice == 0:
            _screen_learn(stdscr, state)
        elif choice == 1:
            _screen_voices(stdscr, state)
        elif choice == 2:
            _screen_script(stdscr, state)
        elif choice == 3:
            _screen_generate(stdscr, state)
        elif choice == 4:
            _screen_record(stdscr, state)
        elif choice == 5:
            _screen_apply_base(stdscr, state)
        elif choice == 6:
            _screen_deploy(stdscr, state)
        elif choice == 7:
            set_ui_lang("en" if get_ui_lang() == "fr" else "fr")


def run_tui() -> None:
    """Launch the interactive ncurses TUI application."""
    curses.wrapper(_tui_main)
