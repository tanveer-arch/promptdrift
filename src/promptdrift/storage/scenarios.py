"""File-based scenario store for .promptdrift/scenarios.json."""

from __future__ import annotations

from pathlib import Path

from promptdrift.models.capture import Scenario, ScenarioLibrary


def load_scenarios(path: Path = Path(".promptdrift/scenarios.json")) -> ScenarioLibrary:
    if not path.is_file():
        return ScenarioLibrary(version=1, scenarios=[])
    try:
        content = path.read_text(encoding="utf-8")
        return ScenarioLibrary.model_validate_json(content)
    except Exception:
        return ScenarioLibrary(version=1, scenarios=[])


def save_scenarios(
    library: ScenarioLibrary, path: Path = Path(".promptdrift/scenarios.json")
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = library.model_dump_json(indent=2) + "\n"
    path.write_text(content, encoding="utf-8")


def add_or_update_scenarios(
    new_scenarios: list[Scenario], path: Path = Path(".promptdrift/scenarios.json")
) -> ScenarioLibrary:
    lib = load_scenarios(path)
    existing_map = {s.id: s for s in lib.scenarios}
    for s in new_scenarios:
        existing_map[s.id] = s
    lib.scenarios = list(existing_map.values())
    save_scenarios(lib, path)
    return lib
