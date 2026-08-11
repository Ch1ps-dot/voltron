import json
from pathlib import Path

import pytest

from voltron.aflnet_seeds import AFLNetSeedError, load_aflnet_seeds


def test_loader_reads_converted_exim_seed():
    root = Path(__file__).resolve().parents[1] / 'config' / 'subjects'
    seeds = load_aflnet_seeds(root, 'exim', 'smtp')
    assert [seed.name for seed in seeds] == [
        'smtp_requests_full', 'smtp_requests_full_bdat',
    ]
    assert all(seed.messages for seed in seeds)


def test_loader_rejects_tampered_length(tmp_path):
    seed_dir = tmp_path / 'exim' / 'aflnet_seeds'
    seed_dir.mkdir(parents=True)
    source = Path(__file__).resolve().parents[1] / 'config' / 'subjects' / 'exim' / 'aflnet_seeds'
    manifest = json.loads((source / 'manifest.json').read_text())
    document = json.loads((source / manifest['seeds'][0]['file']).read_text())
    document['messages'][0]['length'] += 1
    (seed_dir / 'manifest.json').write_text(json.dumps(manifest))
    (seed_dir / manifest['seeds'][0]['file']).write_text(json.dumps(document))
    with pytest.raises(AFLNetSeedError, match='message length mismatch'):
        load_aflnet_seeds(tmp_path, 'exim', 'smtp')
