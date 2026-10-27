"""Publish an explicitly requested GitHub release using the configured Git credential helper.

Credentials stay in memory and are sent only to api.github.com / uploads.github.com.
This script never prints a credential, opens authentication dialogs, or rewrites tags.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--notes', type=Path, required=True)
    parser.add_argument('--asset', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'v\d+\.\d+\.\d+', args.tag):
        raise ValueError('Expected a semantic version tag such as v0.2.0')
    remote = git('remote', 'get-url', 'origin')
    match = re.fullmatch(r'https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?', remote)
    if not match:
        raise ValueError('Only an HTTPS github.com origin is supported')
    owner, repository = match.groups()
    head = git('rev-parse', 'HEAD')
    if git('rev-parse', args.tag + '^{commit}') != head:
        raise ValueError('The release tag must point to the current HEAD')
    if git('status', '--porcelain'):
        raise ValueError('Commit source changes before publishing a release')
    asset = args.asset.resolve()
    if not asset.is_relative_to(ROOT / 'dist') or not asset.is_file() or asset.suffix != '.zip':
        raise ValueError('Release asset must be a source ZIP in dist/')
    credential = subprocess.run(['git', 'credential', 'fill'], cwd=ROOT,
        input='protocol=https\nhost=github.com\n\n', capture_output=True, text=True,
        timeout=30, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'})
    values = dict(line.split('=', 1) for line in credential.stdout.splitlines() if '=' in line)
    token = values.get('password')
    if credential.returncode or not token:
        raise RuntimeError('GitHub credentials are unavailable. Authenticate Git first, then retry.')

    def api(url, method='GET', body=None, binary=False):
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname not in ('api.github.com', 'uploads.github.com'):
            raise ValueError('Unexpected GitHub API host')
        payload = body if binary else json.dumps(body).encode('utf-8') if body is not None else None
        request = Request(url, data=payload, method=method, headers={
            'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': 'Cover-Studio-release',
            'Content-Type': 'application/zip' if binary else 'application/json'})
        try:
            with urlopen(request, timeout=90) as response:
                return json.load(response)
        except HTTPError as error:
            if method == 'GET' and error.code == 404:
                return None
            try:
                message = json.load(error).get('message', 'GitHub API request failed')
            except (ValueError, OSError):
                message = 'GitHub API request failed'
            raise RuntimeError(f'GitHub API {error.code}: {message}') from None

    base = f'https://api.github.com/repos/{owner}/{repository}/releases'
    release = api(base + '/tags/' + quote(args.tag, safe=''))
    if release and not release['draft']:
        print('Release already published: ' + release['html_url'])
        return
    if release is None:
        release = api(base, method='POST', body={'tag_name': args.tag, 'target_commitish': head,
            'name': f'Cover Studio {args.tag} · Professional mode',
            'body': args.notes.read_text(encoding='utf-8'), 'draft': True, 'prerelease': False})
    payload = asset.read_bytes()
    expected = 'sha256:' + hashlib.sha256(payload).hexdigest()
    existing = next((a for a in release.get('assets', []) if a['name'] == asset.name), None)
    if existing:
        if existing.get('digest') != expected:
            raise RuntimeError('An existing draft asset has a different or unavailable digest; refusing to replace it.')
    else:
        upload = release['upload_url'].split('{', 1)[0] + '?name=' + quote(asset.name, safe='')
        result = api(upload, method='POST', body=payload, binary=True)
        if result.get('size') != len(payload) or (result.get('digest') and result['digest'] != expected):
            raise RuntimeError('Uploaded asset verification failed; release remains a draft.')
    published = api(base + '/' + str(release['id']), method='PATCH', body={'draft': False, 'make_latest': 'true'})
    verified = api(base + '/tags/' + quote(args.tag, safe=''))
    if not verified or verified['draft'] or not any(a['name'] == asset.name for a in verified.get('assets', [])):
        raise RuntimeError('Release publication could not be verified')
    print(published['html_url'])
    for item in verified.get('assets', []):
        print(item['browser_download_url'])


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, subprocess.SubprocessError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
