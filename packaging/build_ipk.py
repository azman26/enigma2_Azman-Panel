"""Build the public Panel IPK using Python's standard library only."""
import gzip
import io
import os
from pathlib import Path
import re
import tarfile
from datetime import datetime, timezone

PREFIX = './usr/lib/enigma2/python/Plugins/Extensions/AzmanPanel/'


def tar_gz(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w', format=tarfile.GNU_FORMAT) as archive:
        directories = set()
        for name, data, mode in entries:
            directories.update('./' + p.as_posix().lstrip('./') for p in Path(name).parents if p.as_posix() != '.')
        for name in sorted(directories):
            info = tarfile.TarInfo(name)
            info.type, info.mode = tarfile.DIRTYPE, 0o755
            archive.addfile(info)
        for name, data, mode in entries:
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            info.uname = info.gname = 'root'
            archive.addfile(info, io.BytesIO(data))
    return gzip.compress(output.getvalue(), mtime=0)


def ar(entries):
    output = bytearray(b'!<arch>\n')
    for name, data in entries:
        header = f'{name + "/":<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(data):<10}`\n'
        if len(header) != 60:
            raise ValueError('Invalid ar header')
        output.extend(header.encode('ascii'))
        output.extend(data)
        if len(data) % 2:
            output.extend(b'\n')
    return bytes(output)


def build(source, output, version):
    if not re.fullmatch(r'\d{4}\.\d{2}\.\d{2}-\d{4}', version):
        raise ValueError('Version must have format YYYY.MM.DD-HHMM')
    datetime.strptime(version, '%Y.%m.%d-%H%M')
    source, output = Path(source), Path(output)
    for name in ('constants.py', '__init__.py', 'plugin.py', 'panel_skin.xml', 'plugin.png', 'packaging/control', 'packaging/prerm'):
        if not (source / name).is_file():
            raise ValueError('Missing package input: ' + name)
    if not (source / 'icons').is_dir():
        raise ValueError('Missing icons directory')
    payload = []
    for file in sorted(source.glob('*.py')):
        if file.is_symlink():
            raise ValueError('Source symlinks are not supported')
        text = file.read_text(encoding='utf-8-sig')
        if file.name == 'constants.py':
            text, count = re.subn(r'^PLUGIN_VERSION\s*=.*$', 'PLUGIN_VERSION = "' + version + '"', text, flags=re.M)
            if count != 1:
                raise ValueError('Expected one PLUGIN_VERSION assignment')
        compile(text, file.name, 'exec')
        payload.append((PREFIX + file.name, text.encode('utf-8'), 0o644))
    for file in [source / 'panel_skin.xml', source / 'plugin.png'] + sorted((source / 'icons').rglob('*')):
        if file.is_symlink():
            raise ValueError('Asset symlinks are not supported')
        if file.is_file():
            payload.append((PREFIX + file.relative_to(source).as_posix(), file.read_bytes(), 0o644))
    control = (source / 'packaging/control').read_text(encoding='utf-8-sig').replace('\r', '')
    control, count = re.subn(r'^Version:.*$', 'Version: ' + version, control, flags=re.M)
    if count != 1:
        raise ValueError('Expected one Version field')
    fields = {}
    for line in control.splitlines():
        if line and not line[0].isspace():
            name, sep, value = line.partition(':')
            if not sep or name in fields:
                raise ValueError('Invalid/duplicate control field')
            fields[name] = value.strip()
    for name in ('Package', 'Version', 'Description', 'Architecture', 'Section', 'Priority', 'Maintainer', 'License'):
        if not fields.get(name):
            raise ValueError('Missing control field: ' + name)
    package = fields['Package']
    if not re.fullmatch(r'[a-z0-9][a-z0-9.+-]*', package) or fields['Architecture'] != 'all':
        raise ValueError('Invalid package name or architecture')
    prerm = (source / 'packaging/prerm').read_bytes().replace(b'\r', b'')
    if not prerm.startswith(b'#!/bin/sh\n'):
        raise ValueError('Invalid prerm shebang')
    packed = ar([('debian-binary', b'2.0\n'), ('control.tar.gz', tar_gz([
        ('./control', (control.rstrip() + '\n').encode('utf-8'), 0o644), ('./prerm', prerm, 0o755)])),
        ('data.tar.gz', tar_gz(payload))])
    target = output / 'all' / (package + '_' + version + '_all.ipk')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.ipk.tmp')
    temporary.write_bytes(packed)
    os.replace(temporary, target)
    return target


if __name__ == '__main__':
    version = os.environ.get('VERSION') or datetime.now(timezone.utc).strftime('%Y.%m.%d-%H%M')
    print(build(os.environ.get('SOURCE_DIR', '/source'), os.environ.get('OUTPUT_DIR', '/output'), version))
