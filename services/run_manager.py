import json
import uuid
from datetime import datetime
from pathlib import Path

RUNS_DIR = Path('runs')


def generate_run_id() -> str:
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    short_id  = str(uuid.uuid4())[:8]
    return f'run_{timestamp}_{short_id}'


def create_run_dir(run_id: str) -> Path:
    run_path = RUNS_DIR / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    return run_path


def save_artifact(run_id: str, filename: str, data: dict) -> Path:
    run_path = RUNS_DIR / run_id
    filepath = run_path / filename
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=str)
    return filepath


def load_artifact(run_id: str, filename: str) -> dict:
    filepath = RUNS_DIR / run_id / filename
    with open(filepath, encoding='utf-8') as f:
        return json.load(f)


def artifact_exists(run_id: str, filename: str) -> bool:
    filepath = RUNS_DIR / run_id / filename
    return filepath.exists()


def save_markdown(run_id: str, filename: str, content: str) -> Path:
    run_path = RUNS_DIR / run_id
    filepath = run_path / filename
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return filepath


def get_run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


def list_runs() -> list[str]:
    if not RUNS_DIR.exists():
        return []
    return sorted([
        d.name for d in RUNS_DIR.iterdir()
        if d.is_dir() and d.name.startswith('run_')
    ])


def log_run_start(run_id: str, bundle_path: str) -> None:
    meta = {
        'run_id':      run_id,
        'bundle_path': bundle_path,
        'started_at':  datetime.now().isoformat(),
        'status':      'running'
    }
    save_artifact(run_id, 'run_meta.json', meta)


def log_run_end(run_id: str, decision: str) -> None:
    meta = load_artifact(run_id, 'run_meta.json')
    meta['completed_at'] = datetime.now().isoformat()
    meta['status']       = 'completed'
    meta['decision']     = decision
    save_artifact(run_id, 'run_meta.json', meta)


def get_run_summary(run_id: str) -> dict:
    run_path  = RUNS_DIR / run_id
    artifacts = [f.name for f in run_path.iterdir() if f.is_file()]
    meta = (
        load_artifact(run_id, 'run_meta.json')
        if artifact_exists(run_id, 'run_meta.json') else {}
    )
    return {'run_id': run_id, 'artifacts': artifacts, 'meta': meta}
