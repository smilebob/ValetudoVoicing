"""Catalog of standard Roborock S5 (Gen 2) voicepack sound files."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml


@dataclass(frozen=True)
class SoundSpec:
    """Definition of a single Roborock S5 sound entry."""

    filename: str
    category: str
    description: str
    default_fr: str
    default_en: str
    aliases: tuple[str, ...] = ()


ROBOROCK_S5_SOUNDS: list[SoundSpec] = [
    # --- Nettoyage / Cleaning ---
    SoundSpec("start.wav", "cleaning", "Démarrage du nettoyage", "Démarrage du nettoyage.", "Starting cleaning.", aliases=("start_clean.wav",)),
    SoundSpec("stop.wav", "cleaning", "Arrêt / pause du nettoyage", "Nettoyage arrêté.", "Cleaning stopped.", aliases=("stop_clean.wav",)),
    SoundSpec("pause.wav", "cleaning", "Mise en pause", "Nettoyage en pause.", "Cleaning paused.", aliases=("pause_clean.wav",)),
    SoundSpec("resume.wav", "cleaning", "Reprise du nettoyage", "Reprise du nettoyage.", "Resuming cleaning.", aliases=("resume_clean.wav",)),
    SoundSpec("clean_finish.wav", "cleaning", "Nettoyage terminé, retour à la base", "Nettoyage terminé, retour à la station de charge.", "Finished cleaning. Returning to the dock.", aliases=("finish_clean.wav",)),
    SoundSpec("spot.wav", "cleaning", "Démarrage du nettoyage localisé (Spot)", "Démarrage du nettoyage localisé.", "Starting spot cleaning.", aliases=("spot_clean.wav",)),
    SoundSpec("zone.wav", "cleaning", "Démarrage du nettoyage de zone", "Démarrage du nettoyage de zone.", "Starting zoned cleaning.", aliases=("zone_clean.wav",)),
    SoundSpec("zone_complete.wav", "cleaning", "Nettoyage de zone terminé", "Nettoyage de zone terminé, retour à la base.", "Zoned cleaning complete. Returning to the dock.", aliases=("zone_finish.wav",)),
    SoundSpec("timed_clean.wav", "cleaning", "Démarrage d'un nettoyage programmé", "Démarrage du nettoyage programmé.", "Starting scheduled cleaning."),
    SoundSpec("remote.wav", "cleaning", "Mode contrôle à distance activé", "Contrôle à distance activé.", "Remote control mode activated."),
    SoundSpec("remote_complete.wav", "cleaning", "Fin du contrôle à distance", "Contrôle à distance terminé.", "Remote control mode ended."),

    # --- Base & Batterie / Dock & Battery ---
    SoundSpec("home.wav", "dock", "Retour à la station de charge", "Retour à la station de charge.", "Returning to the dock.", aliases=("back_dock.wav",)),
    SoundSpec("charging.wav", "dock", "En charge sur la station", "En charge.", "Charging."),
    SoundSpec("lowpower.wav", "dock", "Batterie faible, retour à la base", "Batterie faible, retour à la station de charge.", "Low battery. Returning to the dock."),
    SoundSpec("back_dock_failed.wav", "dock", "Station de charge introuvable", "Impossible de trouver la station de charge. Veuillez retirer les obstacles.", "Docking station unreachable. Please remove obstacles."),
    SoundSpec("back_dock_nearby.wav", "dock", "Station de charge obstruée", "Station de charge obstruée. Veuillez dégager l'accès.", "Docking station obstructed. Please remove obstacles."),

    # --- Bac à poussière & Maintenance / Bin & Maintenance ---
    SoundSpec("bin_in.wav", "maintenance", "Bac à poussière installé", "Bac à poussière installé.", "Dustbin installed."),
    SoundSpec("bin_out.wav", "maintenance", "Bac à poussière retiré", "Bac à poussière retiré.", "Dustbin removed."),
    SoundSpec("binout_error10.wav", "maintenance", "Bac retiré, nettoyer le filtre", "Bac à poussière retiré. Pensez à nettoyer le filtre.", "Dustbin removed. Please clean the filter."),
    SoundSpec("clean_bin.wav", "maintenance", "Rappel de vider le bac à poussière", "Veuillez vider le bac à poussière.", "Please empty the dustbin."),

    # --- Localisation & Navigation / Locate & Navigation ---
    SoundSpec("findme.wav", "system", "Localiser le robot (Find Me)", "Coucou, je suis ici !", "Hi, I'm here!"),
    SoundSpec("relocate_start.wav", "system", "Repositionnement en cours", "Repositionnement en cours.", "Repositioning."),
    SoundSpec("relocate_success.wav", "system", "Repositionnement réussi", "Position retrouvée.", "Repositioning succeeded."),
    SoundSpec("relocate_failed.wav", "system", "Échec du repositionnement", "Échec du repositionnement, création d'une nouvelle carte.", "Repositioning failed. Starting a new map."),

    # --- Système & Réseau / System & Network ---
    SoundSpec("power_on.wav", "system", "Allumage du robot", "Bonjour, je suis prêt.", "Powering on."),
    SoundSpec("power_off.wav", "system", "Extinction du robot", "Extinction en cours, au revoir.", "Powering off."),
    SoundSpec("wifi_reset.wav", "system", "Réinitialisation du Wi-Fi", "Réinitialisation de la connexion Wi-Fi.", "Resetting Wi-Fi connection."),
    SoundSpec("reset_factory.wav", "system", "Réinitialisation d'usine", "Réinitialisation aux paramètres d'usine.", "Restoring factory settings."),
    SoundSpec("update.wav", "system", "Mise à jour en cours", "Mise à jour du système en cours.", "Updating system."),
    SoundSpec("update_done.wav", "system", "Mise à jour terminée", "Mise à jour terminée.", "Update complete."),
    SoundSpec("update_fail.wav", "system", "Échec de la mise à jour", "Échec de la mise à jour.", "Update failed."),

    # --- Erreurs / Errors ---
    SoundSpec("error1.wav", "error", "Erreur 1 : Tourelle laser (LDS) bloquée", "Erreur 1 : le capteur laser est bloqué, veuillez le vérifier.", "Error 1: Laser distance sensor blocked."),
    SoundSpec("error2.wav", "error", "Erreur 2 : Pare-chocs coincé", "Erreur 2 : le pare-chocs est coincé, veuillez le tapoter légèrement.", "Error 2: Bumper stuck. Please tap it lightly."),
    SoundSpec("error3.wav", "error", "Erreur 3 : Roue suspendue", "Erreur 3 : une roue est dans le vide, posez-moi sur une surface plane.", "Error 3: Wheel suspended. Please place me on a flat surface."),
    SoundSpec("error4.wav", "error", "Erreur 4 : Capteurs de vide sales", "Erreur 4 : veuillez nettoyer les capteurs de vide sous le robot.", "Error 4: Cliff sensors dirty. Please clean them."),
    SoundSpec("error5.wav", "error", "Erreur 5 : Brosse principale bloquée", "Erreur 5 : la brosse principale est bloquée, veuillez la nettoyer.", "Error 5: Main brush jammed. Please clean it."),
    SoundSpec("error6.wav", "error", "Erreur 6 : Brosse latérale bloquée", "Erreur 6 : la brosse latérale est bloquée, veuillez la nettoyer.", "Error 6: Side brush jammed. Please clean it."),
    SoundSpec("error7.wav", "error", "Erreur 7 : Roue principale bloquée", "Erreur 7 : une roue principale est bloquée, vérifiez qu'il n'y a rien autour.", "Error 7: Main wheel jammed."),
    SoundSpec("error8.wav", "error", "Erreur 8 : Robot coincé", "Erreur 8 : je suis coincé, veuillez dégager les obstacles autour de moi.", "Error 8: Robot trapped. Please clear obstacles around me."),
    SoundSpec("error9.wav", "error", "Erreur 9 : Bac à poussière ou filtre manquant", "Erreur 9 : veuillez installer le bac à poussière et le filtre.", "Error 9: Dustbin or filter missing."),
    SoundSpec("error10.wav", "error", "Erreur 10 : Filtre obstrué ou humide", "Erreur 10 : le filtre est bloqué ou humide, veuillez le nettoyer ou le sécher.", "Error 10: Filter blocked or wet."),
    SoundSpec("error11.wav", "error", "Erreur 11 : Champ magnétique détecté", "Erreur 11 : champ magnétique détecté, veuillez me déplacer.", "Error 11: Strong magnetic field detected."),
    SoundSpec("error12.wav", "error", "Erreur 12 : Batterie critique", "Erreur 12 : batterie très faible, veuillez me poser sur la station de charge.", "Error 12: Battery critically low."),
    SoundSpec("error13.wav", "error", "Erreur 13 : Problème de charge", "Erreur 13 : erreur de charge, nettoyez les contacts de la station.", "Error 13: Charging error. Please clean charging contacts."),
    SoundSpec("error_internal.wav", "error", "Erreur interne", "Erreur interne détectée, veuillez redémarrer le robot.", "Internal error detected. Please restart the robot."),
]

SOUND_ALIASES: dict[str, tuple[str, ...]] = {
    spec.filename: spec.aliases for spec in ROBOROCK_S5_SOUNDS if spec.aliases
}


def build_default_script(lang: str = "fr", name: str = "voicepack") -> dict[str, Any]:
    """Create a default YAML-serializable voicepack script dictionary."""
    sounds_dict: dict[str, dict[str, Any]] = {}
    for spec in ROBOROCK_S5_SOUNDS:
        text = spec.default_fr if lang.lower().startswith("fr") else spec.default_en
        sounds_dict[spec.filename] = {
            "category": spec.category,
            "description": spec.description,
            "enabled": True,
            "text": text,
        }
    return {
        "version": 1,
        "name": name,
        "robot": "roborock_s5",
        "language": lang,
        "sounds": sounds_dict,
    }


def get_script_name(script: dict[str, Any], script_path: Path | None = None) -> str:
    """Return the configured voicepack name from script metadata or fallback to file stem."""
    raw = str(script.get("name", "")).strip()
    if raw:
        return raw
    if script_path is not None:
        return script_path.stem.split(".")[0] or "voicepack"
    return "voicepack"


def save_script(script: dict[str, Any], path: Path) -> None:
    """Save a voicepack script dictionary to YAML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(script, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def load_script(path: Path) -> dict[str, Any]:
    """Load and validate a voicepack YAML script."""
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "sounds" not in data or not isinstance(data["sounds"], dict):
        raise ValueError(f"Invalid voicepack script format in {path}")
    return data
