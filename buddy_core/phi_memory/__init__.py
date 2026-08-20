"""
PhiMemory — Persistent Agent Memory
File-backed. Survives reboots. Syncs via GCS daily.
PHI = 1.618033988749895
"""
import json, time, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.phi_engine import PHI, phi_cycle, phi_hash

STORE_PATH = Path(__file__).parent / 'memory_store.json'

class PhiMemoryStore:
    def __init__(self):
        self.path = STORE_PATH
        self._data = self._load()

    def _load(self):
        if self.path.exists():
            try: return json.loads(self.path.read_text())
            except: return {}
        return {}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2))

    def store(self, agent: str, key: str, value):
        if agent not in self._data:
            self._data[agent] = {}
        self._data[agent][key] = {
            'value': value,
            'phi_cycle': round(phi_cycle(), 8),
            'timestamp': datetime.utcnow().isoformat(),
            'hash': phi_hash(f'{agent}{key}{str(value)}')
        }
        self._save()

    def recall(self, agent: str, key: str, default=None):
        return self._data.get(agent, {}).get(key, {}).get('value', default)

    def log_action(self, agent, action, result, revenue_impact=0.0):
        key = f'_hist_{int(time.time())}'
        self.store(agent, key, {
            'action': action, 'result': result,
            'revenue_impact': revenue_impact
        })

    def get_wins(self, agent):
        mem = self._data.get(agent, {})
        return [v['value'] for k, v in mem.items()
                if k.startswith('_hist') and
                v.get('value', {}).get('revenue_impact', 0) > 0]

    def all_agents(self):
        return [k for k in self._data if not k.startswith('_')]

_store = None
def get_store() -> PhiMemoryStore:
    global _store
    if _store is None:
        _store = PhiMemoryStore()
    return _store

PersistentMemoryStore = PhiMemoryStore
