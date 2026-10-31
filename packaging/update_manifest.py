"""Publish the Panel through GitHub Releases; preserve all other feed entries."""
import json
from pathlib import Path
import re
import sys
from datetime import datetime, timezone


def update(path, repo, tag, version, name, sha):
    if not re.fullmatch(r'\d{4}\.\d{2}\.\d{2}-\d{4}', version) or tag != 'v' + version:
        raise ValueError('Release tag and version differ')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('Invalid repository')
    if name != 'enigma2-plugin-extensions--azman-azmanpanel_' + version + '_all.ipk':
        raise ValueError('Unexpected package filename')
    if not re.fullmatch(r'[0-9a-f]{64}', sha):
        raise ValueError('Invalid SHA256')
    path = Path(path)
    manifest = json.loads(path.read_text(encoding='utf-8-sig'))
    entries = [entry for entry in manifest['packages'] if entry.get('id') == 'azman-panel']
    if len(entries) != 1:
        raise ValueError('Expected one azman-panel entry')
    entry = entries[0]

    def version_key(value):
        return tuple(int(part) for part in re.findall(r'\d+', value))

    if version_key(str(entry.get('version') or '0')) > version_key(version):
        raise ValueError('Refusing to downgrade manifest')
    entry['protected'] = False
    entry['version'] = version
    entry.setdefault('variants', {})['all'] = {
        'ipk': 'all/' + name,
        'url': 'https://github.com/' + repo + '/releases/download/' + tag + '/' + name,
        'sha256': sha,
    }
    manifest['updated'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return True


if __name__ == '__main__':
    update(*sys.argv[1:])
