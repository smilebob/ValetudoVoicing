"""Command-line interface for ValetudoVoicing."""

from pathlib import Path
import re
import tempfile
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
import typer

from .deployer import deploy_to_valetudo
from .discovery import VoiceCandidate, search_character_voices
from .effects import EFFECT_MAP, VOICE_EFFECTS, apply_voice_effect
from .i18n import get_ui_lang, set_ui_lang, tr
from .jingles import JINGLE_MAP, JINGLES, apply_jingle
from .packager import build_pkg, normalize_wav_for_roborock
from .recorder import play_wav, record_until_enter, trim_and_normalize_recording
from .robots import ROBOROCK_PROFILES, detect_robot_from_valetudo, get_robot_profile
from .sounds import build_default_script, get_script_name, load_script, save_script
from .tts import get_backend
from .tui import run_tui
from .voices import delete_voice_profile, list_voice_profiles, load_voice_profile, save_voice_profile
from .youtube import extract_soundboard_voice, extract_youtube_voice

app = typer.Typer(
    name="valetudo-voicing",
    help="Clone voices from YouTube or record your own, apply fun effects, and build Roborock S5 Valetudo voicepacks.",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def main_callback(
    ui_lang: Optional[str] = typer.Option(
        None,
        "--ui-lang",
        help="Interface language (en or fr). Auto-detected from system locale if omitted.",
    ),
) -> None:
    """Configure global UI language."""
    if ui_lang:
        set_ui_lang(ui_lang)
    else:
        get_ui_lang()


def _interactive_edit_script(script: dict, category: Optional[str] = None) -> dict:
    """Walk the user through each sound in the script interactively."""
    sounds: dict = script["sounds"]
    console.print(
        "\n[bold cyan]Édition interactive du voicepack[/bold cyan] "
        "(Entrée = garder la valeur actuelle, '-' = désactiver ce son, 'q' = quitter et sauvegarder)\n"
    )
    for filename, entry in sounds.items():
        if category and entry.get("category") != category:
            continue

        desc = entry.get("description", "")
        current_text = entry.get("text", "")
        enabled = entry.get("enabled", True)
        status = "[green]actif[/green]" if enabled else "[dim]désactivé[/dim]"

        console.print(f"[bold]{filename}[/bold] ({entry.get('category', 'other')}, {status}) — {desc}")
        answer = Prompt.ask("  Texte", default=current_text)

        if answer.strip().lower() == "q":
            break
        if answer.strip() == "-":
            entry["enabled"] = False
            console.print("  [yellow]→ Son désactivé[/yellow]\n")
        else:
            entry["enabled"] = True
            entry["text"] = answer.strip()
            console.print()

    return script


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", text.strip().lower()).strip("_")
    return slug or "voice"


def _format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    mins, secs = divmod(int(seconds), 60)
    return f"{mins}:{secs:02d}"


def _pick_candidate(candidates: list[VoiceCandidate], auto: bool) -> VoiceCandidate:
    if auto or len(candidates) == 1:
        chosen = candidates[0]
        console.print(f"[cyan]Sélection automatique :[/cyan] {chosen.title} ({chosen.source})")
        return chosen

    table = Table(title="Extraits vocaux trouvés")
    table.add_column("#", style="bold cyan", width=3)
    table.add_column("Source", style="magenta")
    table.add_column("Titre")
    table.add_column("Durée", justify="right")
    table.add_column("Chaîne / Origine")

    for idx, cand in enumerate(candidates, start=1):
        table.add_row(
            str(idx),
            cand.source,
            cand.title,
            _format_duration(cand.duration_sec),
            cand.channel or "-",
        )
    console.print(table)

    while True:
        choice = IntPrompt.ask(f"Choisissez un extrait (1-{len(candidates)})", default=1)
        if 1 <= choice <= len(candidates):
            return candidates[choice - 1]
        console.print(f"[red]Veuillez entrer un nombre entre 1 et {len(candidates)}.[/red]")


@app.command()
def learn(
    url: Optional[str] = typer.Argument(None, help="URL de la vidéo YouTube contenant la voix à apprendre."),
    character: Optional[str] = typer.Option(
        None, "--character", "-c", help="Nom du personnage à rechercher automatiquement (sans URL)."
    ),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Nom du profil vocal à enregistrer (déduit du personnage si omis)."
    ),
    start: Optional[str] = typer.Option(None, "--start", "-s", help="Début de l'extrait (ex: 00:00:15)."),
    end: Optional[str] = typer.Option(None, "--end", "-e", help="Fin de l'extrait (ex: 00:00:45)."),
    isolate_vocals: bool = typer.Option(
        False, "--isolate-vocals", help="Sépare la voix de la musique de fond via Demucs (plus lent)."
    ),
    lang: str = typer.Option("fr", "--lang", "-l", help="Langue d'origine recherchée (ex: fr, en, es, ja)."),
    auto: bool = typer.Option(
        False, "--auto", "-a", help="Sélectionner automatiquement le meilleur résultat sans confirmation."
    ),
) -> None:
    """Apprendre une voix depuis une URL YouTube ou par recherche automatique d'un personnage."""
    if not url and not character:
        console.print("[red]Vous devez fournir soit une URL YouTube, soit `--character \"Nom\"`.[/red]")
        raise typer.Exit(code=2)
    if url and character:
        console.print("[red]Utilisez soit une URL YouTube, soit `--character`, pas les deux.[/red]")
        raise typer.Exit(code=2)

    profile_name = name or (_slugify(character) if character else "")
    if not profile_name:
        console.print("[red]L'option `--name` est requise lorsque vous fournissez une URL.[/red]")
        raise typer.Exit(code=2)

    selected_candidate: Optional[VoiceCandidate] = None
    target_url = url or ""

    if character:
        with console.status(f"[bold cyan]Recherche d'extraits vocaux pour '{character}' ({lang})..."):
            candidates = search_character_voices(character=character, lang=lang, limit=5)

        if not candidates:
            console.print(f"[red]Aucun extrait trouvé pour '{character}' ({lang}). Essayez avec une URL YouTube.[/red]")
            raise typer.Exit(code=1)

        selected_candidate = _pick_candidate(candidates, auto=auto)
        target_url = selected_candidate.url

    with console.status("[bold green]Téléchargement et extraction du meilleur segment vocal..."):
        if selected_candidate and selected_candidate.source == "101soundboards" and selected_candidate.audio_urls:
            tmp_dir, wav_path, duration = extract_soundboard_voice(
                audio_urls=selected_candidate.audio_urls,
                isolate_vocals=isolate_vocals,
            )
        else:
            tmp_dir, wav_path, duration = extract_youtube_voice(
                url=target_url,
                start=start,
                end=end,
                isolate_vocals=isolate_vocals,
                auto_trim=bool(character and not start and not end),
            )
        try:
            profile = save_voice_profile(
                name=profile_name,
                reference_wav=wav_path,
                source_url=target_url,
                source_lang=lang,
                isolated_vocals=isolate_vocals,
                duration_sec=duration,
            )
        finally:
            tmp_dir.cleanup()

    console.print(f"[bold green]✓ Profil vocal '{profile.name}' enregistré ![/bold green]")
    console.print(f"  Durée : {profile.duration_sec:.1f}s | Isolation vocale : {profile.isolated_vocals}")
    console.print(f"  Fichier : {profile.reference_wav}")


@app.command()
def voices() -> None:
    """Lister les profils vocaux enregistrés."""
    profiles = list_voice_profiles()
    if not profiles:
        console.print("[yellow]Aucun profil vocal enregistré. Utilisez `valetudo-voicing learn <url> --name <nom>`.[/yellow]")
        return

    table = Table(title="Profils vocaux disponibles")
    table.add_column("Nom", style="bold cyan")
    table.add_column("Langue source")
    table.add_column("Durée")
    table.add_column("Isolation Demucs")
    table.add_column("Source URL")

    for p in profiles:
        table.add_row(
            p.name,
            p.source_lang,
            f"{p.duration_sec:.1f}s",
            "Oui" if p.isolated_vocals else "Non",
            p.source_url,
        )
    console.print(table)


@app.command("delete-voice")
def delete_voice(
    name: str = typer.Argument(..., help="Nom du profil vocal à supprimer."),
) -> None:
    """Supprimer un profil vocal enregistré."""
    if Confirm.ask(f"Supprimer définitivement le profil vocal '{name}' ?"):
        delete_voice_profile(name)
        console.print(f"[green]Profil '{name}' supprimé.[/green]")


@app.command()
def init(
    output: Path = typer.Argument(Path("voicepack.yaml"), help="Chemin du fichier YAML à créer."),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Nom du voicepack (utilisé pour nommer le .pkg)."),
    robot: str = typer.Option("roborock_s5", "--robot", "-R", help="Modèle Roborock (ex: roborock_s5, roborock_s5max, roborock_s7, roborock_q7max...)."),
    robot_ip: Optional[str] = typer.Option(None, "--robot-ip", help="IP Valetudo pour détecter automatiquement le modèle du robot."),
    lang: str = typer.Option("fr", "--lang", "-l", help="Langue des textes par défaut (fr ou en)."),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Saisir/modifier les textes un par un dans le terminal."
    ),
) -> None:
    """Générer un fichier script YAML pré-rempli pour le modèle Roborock choisi."""
    if output.exists() and not Confirm.ask(f"Le fichier {output} existe déjà. L'écraser ?"):
        raise typer.Abort()

    target_robot = robot
    if robot_ip:
        try:
            detected, raw_name = detect_robot_from_valetudo(robot_ip)
            if detected:
                target_robot = detected.id
                console.print(f"[cyan]Modèle détecté via Valetudo : {detected.name} ({raw_name})[/cyan]")
            else:
                console.print(f"[yellow]Modèle '{raw_name}' non reconnu, utilisation de '{target_robot}'.[/yellow]")
        except Exception as exc:
            console.print(f"[yellow]Détection Valetudo impossible ({exc}), utilisation de '{target_robot}'.[/yellow]")

    get_robot_profile(target_robot)
    pack_name = name or (output.stem.split(".")[0] or "voicepack")
    script = build_default_script(lang=lang, name=pack_name, robot=target_robot)
    if interactive:
        script = _interactive_edit_script(script)

    save_script(script, output)
    console.print(f"[bold green]✓ Script voicepack '{pack_name}' ({target_robot}, {len(script['sounds'])} sons) créé : {output}[/bold green]")


@app.command()
def edit(
    script_path: Path = typer.Argument(..., help="Fichier YAML du voicepack à éditer."),
    category: Optional[str] = typer.Option(
        None, "--category", "-c", help="Filtrer par catégorie (cleaning, dock, maintenance, system, error)."
    ),
) -> None:
    """Saisir ou modifier interactivement les textes de chaque son du voicepack."""
    script = load_script(script_path)
    script = _interactive_edit_script(script, category=category)
    save_script(script, script_path)
    console.print(f"[bold green]✓ Modifications enregistrées dans {script_path}[/bold green]")


@app.command()
def generate(
    script_path: Path = typer.Argument(..., help="Fichier YAML contenant les textes du voicepack."),
    voice: str = typer.Option(..., "--voice", "-v", help="Nom du profil vocal appris à utiliser."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Chemin du .pkg (défaut : <nom_du_pack>.pkg)."),
    backend: str = typer.Option("xtts", "--backend", "-b", help="Moteur TTS local : xtts (défaut) ou chatterbox."),
    lang: Optional[str] = typer.Option(None, "--lang", "-l", help="Langue cible de synthèse (ex: fr, en, es, ja...)."),
    effect: str = typer.Option("none", "--effect", "-E", help="Effet vocal amusant à appliquer (ex: vador, c3po, r2d2, kylo...)."),
    jingle: str = typer.Option("none", "--jingle", "-j", help="Jingle d'intro (startrek, r2d2, gong, chime, portal)."),
    only: Optional[str] = typer.Option(None, "--only", help="Régénérer uniquement ce son (ex: start.wav)."),
    keep_wavs: Optional[Path] = typer.Option(None, "--keep-wavs", help="Dossier où conserver les .wav générés."),
    audio_format: str = typer.Option("wav", "--format", "-f", help="Format audio dans le .pkg : wav (défaut) ou ogg."),
    no_encrypt: bool = typer.Option(False, "--no-encrypt", help="Ne pas chiffrer avec ccrypt (produit un .tar.gz)."),
) -> None:
    """Synthétiser tous les sons (ou un seul via --only) et empaqueter le voicepack .pkg."""
    if effect.strip().lower() not in EFFECT_MAP:
        console.print(f"[red]Effet inconnu '{effect}'. Lancez `valetudo-voicing effects` pour voir la liste.[/red]")
        raise typer.Exit(code=2)
    if jingle.strip().lower() not in JINGLE_MAP:
        console.print(f"[red]Jingle inconnu '{jingle}'. Lancez `valetudo-voicing jingles` pour voir la liste.[/red]")
        raise typer.Exit(code=2)

    script = load_script(script_path)
    pack_name = get_script_name(script, script_path)
    target_out = out if out is not None else Path(f"{pack_name}.pkg")
    profile = load_voice_profile(voice)
    target_lang = lang or str(script.get("language", "fr"))

    enabled_items = [
        (fname, entry)
        for fname, entry in script["sounds"].items()
        if entry.get("enabled", True)
        and str(entry.get("text", "")).strip()
        and (not only or fname == only)
    ]
    if not enabled_items:
        console.print("[red]Aucun son actif correspondant dans le script.[/red]")
        raise typer.Exit(code=1)

    tts = get_backend(backend)
    with console.status(f"[bold cyan]Chargement du modèle {tts.name} sur CPU..."):
        tts.load()

    with tempfile.TemporaryDirectory(prefix="valetudo_gen_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        raw_dir = tmp_path / "raw"
        norm_dir = keep_wavs if keep_wavs else (tmp_path / "wavs")
        raw_dir.mkdir(parents=True, exist_ok=True)
        norm_dir.mkdir(parents=True, exist_ok=True)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Synthèse des sons...", total=len(enabled_items))
            for fname, entry in enabled_items:
                progress.update(task, description=f"Synthèse de {fname}...")
                raw_wav = raw_dir / fname
                norm_wav = norm_dir / fname
                tts.synthesize(
                    text=str(entry["text"]).strip(),
                    speaker_wav=profile.reference_wav,
                    language=target_lang,
                    output_wav=raw_wav,
                )
                normalize_wav_for_roborock(raw_wav, norm_wav)
                if effect.strip().lower() != "none":
                    apply_voice_effect(norm_wav, effect)
                if jingle.strip().lower() != "none":
                    apply_jingle(norm_wav, jingle)
                progress.advance(task)

        with console.status("[bold cyan]Empaquetage du voicepack..."):
            pkg_path, md5_hex = build_pkg(norm_dir, target_out, encrypt=not no_encrypt, audio_format=audio_format)

    console.print(f"\n[bold green]✓ Voicepack généré avec succès : {pkg_path}[/bold green]")
    console.print(f"  Sons traités : {len(enabled_items)} | Langue : {target_lang} | Moteur : {tts.name}")
    console.print(f"  MD5 : [bold]{md5_hex}[/bold]")


@app.command()
def record(
    script_path: Path = typer.Argument(..., help="Fichier YAML contenant la liste des phrases à dicter."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Chemin du .pkg (défaut : <nom_du_pack>.pkg)."),
    category: Optional[str] = typer.Option(
        None, "--category", "-c", help="Filtrer par catégorie (cleaning, dock, maintenance, system, error)."
    ),
    only: Optional[str] = typer.Option(None, "--only", help="Ré-enregistrer uniquement ce son (ex: start.wav)."),
    keep_wavs: Optional[Path] = typer.Option(
        None, "--keep-wavs", help="Dossier des .wav (défaut : ./recordings/<nom_du_pack>/)."
    ),
    device: str = typer.Option("default", "--device", "-d", help="Périphérique ALSA d'enregistrement (ex: default, hw:0,0)."),
    effect: str = typer.Option("none", "--effect", "-E", help="Effet vocal amusant à appliquer (ex: vador, c3po, r2d2, kylo...)."),
    jingle: str = typer.Option("none", "--jingle", "-j", help="Jingle d'intro (startrek, r2d2, gong, chime, portal)."),
    audio_format: str = typer.Option("wav", "--format", "-f", help="Format audio dans le .pkg : wav (défaut) ou ogg."),
    no_encrypt: bool = typer.Option(False, "--no-encrypt", help="Ne pas chiffrer avec ccrypt (produit un .tar.gz)."),
) -> None:
    """Dicter interactivement chaque phrase au microphone avec votre propre voix et générer le .pkg."""
    if effect.strip().lower() not in EFFECT_MAP:
        console.print(f"[red]Effet inconnu '{effect}'. Lancez `valetudo-voicing effects` pour voir la liste.[/red]")
        raise typer.Exit(code=2)
    if jingle.strip().lower() not in JINGLE_MAP:
        console.print(f"[red]Jingle inconnu '{jingle}'. Lancez `valetudo-voicing jingles` pour voir la liste.[/red]")
        raise typer.Exit(code=2)

    script = load_script(script_path)
    pack_name = get_script_name(script, script_path)
    target_out = out if out is not None else Path(f"{pack_name}.pkg")
    norm_dir = keep_wavs if keep_wavs is not None else (Path("recordings") / pack_name)
    norm_dir.mkdir(parents=True, exist_ok=True)

    items = [
        (fname, entry)
        for fname, entry in script["sounds"].items()
        if entry.get("enabled", True)
        and (not category or entry.get("category") == category)
        and (not only or fname == only)
    ]
    if not items:
        console.print("[red]Aucun son actif correspondant trouvé dans le script.[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"\n[bold cyan]Dictée vocale interactive — Pack '{pack_name}'[/bold cyan]\n"
        f"Dossier de sauvegarde : [dim]{norm_dir}[/dim]\n"
        "Commandes : [bold]Entrée[/bold] = enregistrer, [bold]s[/bold] = passer, [bold]q[/bold] = terminer et empaqueter.\n"
    )

    with tempfile.TemporaryDirectory(prefix="valetudo_rec_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        raw_dir = tmp_path / "raw"
        staged_dir = tmp_path / "staged"
        raw_dir.mkdir(parents=True, exist_ok=True)
        staged_dir.mkdir(parents=True, exist_ok=True)

        recorded_count = 0
        quit_early = False

        for idx, (fname, entry) in enumerate(items, start=1):
            if quit_early:
                break

            done_now = sum(1 for f, _ in items if (norm_dir / f).exists())
            pct = int(100 * done_now / len(items))
            bar_w = 24
            filled = int(bar_w * done_now / len(items))
            bar = "█" * filled + "░" * (bar_w - filled)
            console.print(f"[cyan]Progression : [{bar}] {done_now}/{len(items)} ({pct}%)[/cyan]")

            norm_wav = norm_dir / fname
            raw_wav = raw_dir / fname
            staged_wav = staged_dir / fname
            desc = entry.get("description", "")
            text = str(entry.get("text", "")).strip()

            console.print(f"[bold]({idx}/{len(items)}) {fname}[/bold] — {desc}")
            console.print(f"  Phrase suggérée : [bold yellow]« {text} »[/bold yellow]")
            if norm_wav.exists():
                console.print("  [green](Déjà enregistré — Entrée pour remplacer, 's' pour conserver)[/green]")

            action = Prompt.ask("  Action", choices=["", "s", "q"], default="", show_choices=False).strip().lower()
            if action == "q":
                break
            if action == "s":
                console.print("  [dim]→ Conservé/Ignoré[/dim]\n")
                continue

            while True:
                console.print("  [bold red]🎙️  Enregistrement en cours...[/bold red] Appuyez sur [bold]Entrée[/bold] pour arrêter.")
                dur = record_until_enter(raw_wav, device=device)
                # Keep clean base recording in norm_dir without effects
                trim_and_normalize_recording(raw_wav, norm_wav)
                apply_voice_effect(norm_wav, effect, output_wav=staged_wav)
                if jingle.strip().lower() != "none":
                    apply_jingle(staged_wav, jingle)
                console.print(f"  [green]Enregistré ({dur:.1f}s)[/green]")

                play_wav(staged_wav)

                post = Prompt.ask(
                    "  [o] Garder / [r] Ré-enregistrer / [e] Réécouter / [s] Passer / [q] Terminer",
                    choices=["o", "r", "e", "s", "q"],
                    default="o",
                    show_choices=False,
                ).strip().lower()

                while post == "e":
                    play_wav(staged_wav)
                    post = Prompt.ask(
                        "  [o] Garder / [r] Ré-enregistrer / [e] Réécouter / [s] Passer / [q] Terminer",
                        choices=["o", "r", "e", "s", "q"],
                        default="o",
                        show_choices=False,
                    ).strip().lower()

                if post == "r":
                    continue
                if post == "s":
                    if norm_wav.exists():
                        norm_wav.unlink()
                    if staged_wav.exists():
                        staged_wav.unlink()
                    console.print("  [dim]→ Ignoré[/dim]\n")
                    break
                if post == "q":
                    recorded_count += 1
                    quit_early = True
                    console.print()
                    break

                recorded_count += 1
                console.print()
                break

        base_wavs = sorted(norm_dir.glob("*.wav"))
        if not base_wavs:
            console.print("[yellow]Aucun son enregistré, empaquetage annulé.[/yellow]")
            raise typer.Exit(code=0)

        # Ensure any previously recorded base wavs also get effect+jingle in staged_dir
        with console.status("[bold cyan]Application des effets et empaquetage du voicepack..."):
            for bw in base_wavs:
                sw = staged_dir / bw.name
                if not sw.exists():
                    apply_voice_effect(bw, effect, output_wav=sw)
                    if jingle.strip().lower() != "none":
                        apply_jingle(sw, jingle)
            pkg_path, md5_hex = build_pkg(staged_dir, target_out, encrypt=not no_encrypt, audio_format=audio_format)

    console.print(f"[bold green]✓ Voicepack personnel généré : {pkg_path}[/bold green]")
    console.print(f"  Pack de base propre conservé dans : {norm_dir}")
    console.print(f"  Sons inclus : {len(base_wavs)} (enregistrés durant cette session : {recorded_count})")
    console.print(f"  MD5 : [bold]{md5_hex}[/bold]")


@app.command("apply-effect")
def apply_effect_cmd(
    source: str = typer.Argument(..., help="Nom d'un pack de base (dans ./recordings/) ou dossier de fichiers .wav."),
    effect: str = typer.Option("none", "--effect", "-E", help="Effet vocal à appliquer (ex: vador, c3po, r2d2, kylo...)."),
    jingle: str = typer.Option("none", "--jingle", "-j", help="Jingle d'intro (startrek, r2d2, gong, chime, portal)."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Chemin du .pkg de sortie (défaut: <nom>_<effet>.pkg)."),
    audio_format: str = typer.Option("wav", "--format", "-f", help="Format audio dans le .pkg : wav (défaut) ou ogg."),
    no_encrypt: bool = typer.Option(False, "--no-encrypt", help="Ne pas chiffrer avec ccrypt (produit un .tar.gz)."),
) -> None:
    """Créer un nouveau .pkg avec effet/jingle à partir d'un pack d'enregistrement personnel existant."""
    if effect.strip().lower() not in EFFECT_MAP:
        console.print(f"[red]Effet inconnu '{effect}'. Lancez `valetudo-voicing effects` pour voir la liste.[/red]")
        raise typer.Exit(code=2)
    if jingle.strip().lower() not in JINGLE_MAP:
        console.print(f"[red]Jingle inconnu '{jingle}'. Lancez `valetudo-voicing jingles` pour voir la liste.[/red]")
        raise typer.Exit(code=2)

    src_path = Path(source)
    if not src_path.is_dir():
        candidate = Path("recordings") / source
        if candidate.is_dir():
            src_path = candidate
        else:
            console.print(f"[red]Dossier ou pack de base introuvable : {source}[/red]")
            raise typer.Exit(code=1)

    wavs = sorted(src_path.glob("*.wav"))
    if not wavs:
        console.print(f"[red]Aucun fichier .wav trouvé dans {src_path}[/red]")
        raise typer.Exit(code=1)

    target_out = out if out is not None else Path(f"{src_path.name}_{effect.lower()}.pkg")
    with tempfile.TemporaryDirectory(prefix="valetudo_fx_pack_") as tmp_dir:
        staged_dir = Path(tmp_dir)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Traitement des sons...", total=len(wavs))
            for w in wavs:
                progress.update(task, description=f"Application de '{effect}' sur {w.name}...")
                dst = staged_dir / w.name
                apply_voice_effect(w, effect, output_wav=dst)
                if jingle.strip().lower() != "none":
                    apply_jingle(dst, jingle)
                progress.advance(task)

        with console.status("[bold cyan]Empaquetage du voicepack..."):
            pkg_path, md5_hex = build_pkg(staged_dir, target_out, encrypt=not no_encrypt, audio_format=audio_format)

    console.print(f"[bold green]✓ Nouveau voicepack généré : {pkg_path}[/bold green]")
    console.print(f"  Base utilisée : {src_path} ({len(wavs)} sons) | Effet : {effect} | Jingle : {jingle}")
    console.print(f"  MD5 : [bold]{md5_hex}[/bold]")


@app.command()
def deploy(
    pkg_path: Path = typer.Argument(..., help="Fichier .pkg à envoyer au robot."),
    robot_ip: str = typer.Option(..., "--robot-ip", "-r", help="Adresse IP locale du Roborock sous Valetudo."),
    lang: str = typer.Option("fr", "--lang", "-l", help="Code langue transmis à Valetudo (ex: fr, en)."),
    port: int = typer.Option(8765, "--port", "-p", help="Port HTTP temporaire local."),
) -> None:
    """Déployer directement un voicepack .pkg sur le robot via l'API Valetudo."""
    try:
        detected, raw_name = detect_robot_from_valetudo(robot_ip, timeout=3.0)
        if detected:
            console.print(f"[cyan]Robot détecté : {detected.name} ({raw_name})[/cyan]")
    except Exception:
        pass
    with console.status(f"[bold cyan]Envoi de {pkg_path.name} vers Valetudo ({robot_ip})..."):
        result = deploy_to_valetudo(pkg_path=pkg_path, robot_ip=robot_ip, language=lang, port=port)

    if result["downloaded"]:
        console.print(f"[bold green]✓ Voicepack téléchargé par le robot ![/bold green]")
    else:
        console.print(f"[yellow]⚠ Requête envoyée à Valetudo, mais le téléchargement n'a pas été confirmé dans le délai imparti.[/yellow]")
    console.print(f"  URL servie : {result['url']}")
    console.print(f"  MD5 : {result['md5']}")


@app.command()
def robots() -> None:
    """Lister tous les modèles d'aspirateurs Roborock supportés sous Valetudo."""
    table = Table(title="Modèles Roborock supportés (--robot)")
    table.add_column("ID (--robot)", style="bold cyan")
    table.add_column("Modèle", style="magenta")
    table.add_column("Fonctionnalités")
    table.add_column("Format")
    for r in ROBOROCK_PROFILES:
        table.add_row(r.id, r.name, ", ".join(r.features), r.audio_format)
    console.print(table)


@app.command()
def effects() -> None:
    """Lister tous les effets vocaux amusants disponibles (--effect)."""
    table = Table(title="Effets vocaux disponibles")
    table.add_column("ID (--effect)", style="bold cyan")
    table.add_column("Nom", style="magenta")
    table.add_column("Description")
    for fx in VOICE_EFFECTS:
        table.add_row(fx.id, fx.name, fx.description)
    console.print(table)


@app.command()
def jingles() -> None:
    """Lister tous les jingles d'intro disponibles (--jingle)."""
    table = Table(title="Jingles d'intro disponibles")
    table.add_column("ID (--jingle)", style="bold cyan")
    table.add_column("Nom", style="magenta")
    table.add_column("Description")
    for j in JINGLES:
        table.add_row(j.id, j.name, j.description)
    console.print(table)


@app.command("preview-effect")
def preview_effect(
    effect: str = typer.Argument(..., help="ID de l'effet à tester (ex: vador, c3po, r2d2, kylo...)."),
    voice: Optional[str] = typer.Option(None, "--voice", "-v", help="Profil vocal appris à utiliser comme échantillon."),
    base: Optional[str] = typer.Option(None, "--base", "-b", help="Nom d'un pack de base (dans ./recordings/) à utiliser."),
    wav: Optional[Path] = typer.Option(None, "--wav", "-w", help="Fichier WAV local à utiliser comme échantillon."),
    jingle: str = typer.Option("none", "--jingle", "-j", help="Jingle d'intro à préécouter."),
) -> None:
    """Préécouter rapidement un effet vocal et/ou un jingle."""
    if effect.strip().lower() not in EFFECT_MAP:
        console.print(f"[red]Effet inconnu '{effect}'.[/red]")
        raise typer.Exit(code=2)
    if jingle.strip().lower() not in JINGLE_MAP:
        console.print(f"[red]Jingle inconnu '{jingle}'.[/red]")
        raise typer.Exit(code=2)

    src_wav: Optional[Path] = wav
    if not src_wav and base:
        base_dir = Path(base) if Path(base).is_dir() else (Path("recordings") / base)
        if base_dir.is_dir():
            import numpy as np
            import soundfile as sf
            wavs = sorted(base_dir.glob("*.wav"))
            for w in wavs:
                try:
                    data, sr = sf.read(str(w), dtype="float32")
                    if len(data) >= int(0.3 * sr) and float(np.max(np.abs(data))) > 0.01:
                        src_wav = w
                        break
                except Exception:
                    continue
            if not src_wav and wavs:
                src_wav = wavs[0]
    if not src_wav and voice:
        src_wav = load_voice_profile(voice).reference_wav
    if not src_wav:
        profiles = list_voice_profiles()
        if profiles:
            src_wav = profiles[0].reference_wav

    with tempfile.TemporaryDirectory(prefix="valetudo_preview_") as tmp_dir:
        out_wav = Path(tmp_dir) / "preview.wav"
        if src_wav and src_wav.exists():
            normalize_wav_for_roborock(src_wav, out_wav)
            apply_voice_effect(out_wav, effect)
        else:
            # Generate a 1s test tone if no voice/wav exists yet
            import numpy as np
            import soundfile as sf
            sr = 16000
            t = np.linspace(0, 1.0, sr, endpoint=False, dtype="float32")
            sf.write(str(out_wav), 0.35 * np.sin(2 * np.pi * 220 * t), sr, subtype="PCM_16")
            apply_voice_effect(out_wav, effect)

        if jingle.strip().lower() != "none":
            apply_jingle(out_wav, jingle)
        console.print(f"[cyan]Lecture de la pré-écoute (effet={effect}, jingle={jingle})...[/cyan]")
        play_wav(out_wav)


@app.command()
def tui() -> None:
    """Lancer l'interface globale ncurses couvrant tout le workflow."""
    run_tui()
