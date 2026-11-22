#!/usr/bin/env python3
"""Write a sanitized, idempotent GitHub #22 failure receipt for signed-release CI.

Only runs for failed/cancelled existing release verification jobs on trusted main.
No VPS access, no secrets copied, no authorization changes and no rollback.
"""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

REPO = 'momopuke/judun-deploy'
ISSUE = 22
API = 'https://api.github.com/repos/' + REPO
STATUSES = frozenset(('success', 'failure', 'cancelled', 'skipped'))
JOBS = (
    ('original_signed_production', 'JUDUN_VERIFY_RESULT'),
    ('release_change_classification', 'JUDUN_CLASSIFY_RESULT'),
    ('offline_guard', 'JUDUN_OFFLINE_RESULT'),
    ('dual_site_minute_recheck', 'JUDUN_DUAL_RESULT'),
)


class ReportError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_meta(run, attempt, sha, results):
    if not re.fullmatch(r'[0-9]{1,20}', str(run)) or int(run) <= 0:
        raise ReportError('INVALID_RUN_ID')
    if not re.fullmatch(r'[0-9]{1,6}', str(attempt)) or int(attempt) <= 0:
        raise ReportError('INVALID_ATTEMPT')
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ReportError('INVALID_COMMIT_SHA')
    if set(results) != {name for name, _ in JOBS}:
        raise ReportError('INVALID_JOB_LIST')
    if any(status not in STATUSES for status in results.values()):
        raise ReportError('INVALID_JOB_STATUS')


def build_failure(run, attempt, sha, results):
    validate_meta(run, attempt, sha, results)
    failures = [(name, status) for name, status in results.items()
                if status in ('failure', 'cancelled')]
    if not failures:
        return None
    marker = 'JUDUN_POSTRELEASE_AUTO_FAILURE_RUN_' + str(run) + '_ATTEMPT_' + str(attempt)
    parts = [
        '### 居盾已簽發布驗證：自動失敗回執（非人工上線宣告）',
        '',
        '<!-- ' + marker + ' -->',
        '**狀態：BLOCKED，需要原受權發布專責檢查；不代表正式站已下線。**',
        '',
        '- 原始 GitHub Actions 回執：https://github.com/' + REPO + '/actions/runs/' + str(run),
        '- PR/主線 commit：' + sha,
        '- Run attempt：' + str(attempt),
        '- 失敗 job：' + ', '.join(name + '=' + status for name, status in failures),
        '- 所有工作狀態：' + ', '.join(name + '=' + results[name] for name, _ in JOBS),
        '',
        '**自動安全處置：**沒有下載私有候選、沒有自動重簽或重新部署、沒有操作付款/DB，也沒有使用 GitHub Actions 擅自回滾。確認根因需看上列原始 run steps；不得把初始健康檢查或有權限憑證缺失誤認為兩站部署完成。',
        '',
        '**固定下一步：**先檢查原簽章來源及 GitHub release gate、已授權 staging health、原 VPS 代理真實安裝／rollback 回執；區分授權缺失、身分漂移、業務功能與真正站點故障。找到根因才做最小修正與重新驗收，不反覆執行無關命令。',
    ]
    return marker, '\n'.join(parts) + '\n'


def api_call(method, endpoint, token, data=None):
    if not isinstance(token, str) or len(token) < 10:
        raise ReportError('GH_TOKEN_MISSING')
    if not endpoint.startswith('/issues/22'):
        raise ReportError('OUT_OF_SCOPE_ENDPOINT')
    raw = None if data is None else json.dumps(data).encode('utf-8')
    req = Request(
        API + endpoint, method=method, data=raw,
        headers={'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28',
                 'Authorization': 'Bearer ' + token,
                 'Content-Type': 'application/json'},
    )
    with build_opener(NoRedirect()).open(req, timeout=20) as r:
        result = r.read(2000000)
        if r.status not in (200, 201) or r.geturl() != req.full_url or len(result) >= 2000000:
            raise ReportError('GITHUB_RESPONSE_INVALID')
    return json.loads(result)


def submit_failure(run, attempt, sha, results, token, request=api_call):
    report = build_failure(run, attempt, sha, results)
    if report is None:
        return 'NOT_NEEDED'
    marker, body = report

    # List only the latest 100 comments for idempotency. Authenticate its
    # author too: a public issue commenter cannot spoof our own run marker.
    info = request('GET', '/issues/22', token)
    count = info.get('comments')
    if type(count) is not int or count < 0:
        raise ReportError('COMMENT_COUNT_UNKNOWN')
    page = max(1, (count - 1) // 100 + 1)
    recent = request('GET', '/issues/22/comments?per_page=100&page=' + str(page), token)
    if not isinstance(recent, list):
        raise ReportError('COMMENTS_SHAPE')
    if any(isinstance(item, dict)
           and isinstance(item.get('user'), dict)
           and item['user'].get('login') == 'github-actions[bot]'
           and marker in str(item.get('body', ''))
           for item in recent):
        return 'ALREADY_RECORDED'
    request('POST', '/issues/22/comments', token, {'body': body})
    return 'CREATED'


def run():
    try:
        results = {name: os.environ.get(env, '') for name, env in JOBS}
        result = submit_failure(
            os.environ.get('GITHUB_RUN_ID', ''),
            os.environ.get('GITHUB_RUN_ATTEMPT', ''),
            os.environ.get('GITHUB_SHA', ''),
            results,
            os.environ.get('GITHUB_TOKEN', ''),
        )
    except (ReportError, OSError, URLError, HTTPError, ValueError, TypeError, KeyError):
        print('JUDUN_RELEASE_FAILURE_REPORT_BLOCKED', file=sys.stderr)
        return 2
    print('JUDUN_RELEASE_FAILURE_REPORT_' + result)
    return 0


if __name__ == '__main__':
    raise SystemExit(run())
