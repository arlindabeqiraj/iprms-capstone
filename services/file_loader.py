import json
import csv
import yaml
from pathlib import Path
from models import BundleManifest


def load_manifest(bundle_path: str) -> BundleManifest:
    path = Path(bundle_path) / 'manifest.yaml'
    with open(path, encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return BundleManifest(**data)


def load_requisition(bundle_path: str) -> dict:
    path = Path(bundle_path) / 'requisition.json'
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_budget_snapshot(bundle_path: str) -> list[dict]:
    path = Path(bundle_path) / 'budget_snapshot.csv'
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))


def load_approved_vendors(bundle_path: str) -> list[dict]:
    path = Path(bundle_path) / 'approved_vendors.csv'
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))


def load_catalogue_pricing(bundle_path: str) -> list[dict]:
    path = Path(bundle_path) / 'catalogue_pricing.csv'
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))


def load_approval_policy(bundle_path: str) -> dict:
    path = Path(bundle_path) / 'approval_policy.yaml'
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_cost_center_mapping(bundle_path: str) -> list[dict]:
    path = Path(bundle_path) / 'cost_center_mapping.csv'
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))


def load_pr_bundle(bundle_path: str) -> dict:
    return {
        'manifest':            load_manifest(bundle_path).model_dump(mode='json'),
        'requisition':         load_requisition(bundle_path),
        'budget_snapshot':     load_budget_snapshot(bundle_path),
        'approved_vendors':    load_approved_vendors(bundle_path),
        'catalogue_pricing':   load_catalogue_pricing(bundle_path),
        'approval_policy':     load_approval_policy(bundle_path),
        'cost_center_mapping': load_cost_center_mapping(bundle_path),
    }
