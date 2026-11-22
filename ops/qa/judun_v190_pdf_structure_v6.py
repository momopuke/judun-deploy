#!/usr/bin/env python3
"""Stage-only PDF structure QA after confirmed v5 four-grid 4/4.

No production app imports, direct DB edits, release signatures, payments,
operating-system package installation or app/worker changes. Reuses the pinned
v5 controller and its native worker, with one extra isolated PDF reader wheel.
"""
import hashlib
import os
from pathlib import Path
import runpy
import stat
import subprocess
import sys

V5 = Path('/root/judun_v190_stage_finalize_v5.py')
V5_SHA = '5a85fd7e854ed0b475837f1e35d36984248fc3a617b5a72db92164ceb280eb89'
WHEEL_SHA = '014dcff867fd99fc0b6fc90ed1f7e1347ef2317ae038a489c2caa64106d268f4'
WHEEL_NAME = 'pypdf-6.4.2-py3-none-any.whl'


def fail(reason):
    raise SystemExit('STOP_' + reason)


def read_pinned(path, digest):
    if path.is_symlink() or not path.is_file():
        fail('QA_SOURCE_INVALID')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        fail('QA_SOURCE_SHA_MISMATCH')
    return data


def main():
    if os.geteuid() != 0:
        fail('NEEDS_ROOT_FINALSHELL')
    if len(sys.argv) != 2:
        fail('WHEEL_ARGUMENT_REQUIRED')
    wheel = Path(sys.argv[1])
    if wheel.name != WHEEL_NAME or wheel.is_symlink() or not wheel.is_file():
        fail('WHEEL_NOT_PINNED')
    if not wheel.parent.name.startswith('judun-v190-pdfqa.') or wheel.parent.parent != Path('/run'):
        fail('WHEEL_OUTSIDE_EPHEMERAL_RUN')
    for x in (wheel, wheel.parent):
        st = x.lstat()
        if st.st_uid != 0 or st.st_mode & 0o022:
            fail('WHEEL_OWNERSHIP_OR_MODE_UNSAFE')
    if not stat.S_ISREG(wheel.stat().st_mode):
        fail('WHEEL_FILE_NOT_REGULAR')
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != WHEEL_SHA:
        fail('WHEEL_SHA_MISMATCH')
    if not os.access(wheel, os.R_OK):
        fail('WHEEL_UNREADABLE')
    source = read_pinned(V5, V5_SHA)
    if b'WORKER=r\'\'\'' not in source:
        fail('V5_WORKER_INVALID')
    v5 = runpy.run_path(str(V5), run_name='judun_v5_safe_import')
    print('V5_SOURCE_AND_PYPDF_WHEEL_SHA=PASS', flush=True)
    jobid = v5['preflight']()
    pid, cwd, cmd, env, uid, gid, groups, appdir, runners, mode = v5['stage_process']()
    prefix = v5['stage_namespace_prefix'](pid, cmd, uid, gid, groups)
    env.update(PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    # -I ignores host PYTHONPATH, so reader is explicitly added in the worker.
    prelude = "sys.path.insert(0, sys.argv[3])\nfrom pypdf import PdfReader\n"
    needle = 'import app as a\n'
    if v5['WORKER'].count(needle) != 1:
        fail('WORKER_PATCH_TARGET_NOT_UNIQUE')
    worker = v5['WORKER'].replace(needle, prelude + needle)
    # Read document's entire page tree and every page content stream.
    original = "pages=len(PdfReader(str(pdf),strict=True).pages);tool='pypdf'"
    strengthened = '''reader=PdfReader(str(pdf),strict=True)
        pages=len(reader.pages)
        if not 1 <= pages <= 200:die('PDF_PAGES_OUT_OF_RANGE')
        for number,page in enumerate(reader.pages,1):
            w,h=float(page.mediabox.width),float(page.mediabox.height)
            if not (100 <= w <= 3000 and 100 <= h <= 3000):die('PDF_PAGE_BOX_INVALID_'+str(number))
            contents=page.get_contents()
            if contents is None:die('PDF_PAGE_HAS_NO_CONTENT_'+str(number))
            stream=contents.get_data()
            if not isinstance(stream,bytes) or len(stream)<10:die('PDF_PAGE_CONTENT_INVALID_'+str(number))
        tool='pypdf' '''.rstrip()
    if worker.count(original) != 1:
        fail('PDF_STRICT_VALIDATION_ANCHOR_NOT_UNIQUE')
    worker = worker.replace(original, strengthened)
    if worker.count('from pypdf import PdfReader') != 2:
        fail('PDF_READER_REQUIREMENT_MISSING')
    compile(worker, 'v6-stage-native-worker', 'exec')
    chosen = None
    for runner in runners:
        if not runner.is_file() or not os.access(runner, os.X_OK):
            continue
        try:
            probe = subprocess.run(
                [*prefix, str(runner), '-I', '-B', '-c',
                 'import sys;sys.path.insert(0,sys.argv[1]);'
                 'import pypdf,fastapi,sqlalchemy,google.genai;'
                 'from pathlib import Path;'
                 'assert Path("/var/lib/judun-staging/app_data.db").is_file()',
                 str(wheel)],
                cwd=str(appdir), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=15,
            )
            if probe.returncode == 0:
                chosen = runner
                break
        except Exception:
            continue
    if chosen is None:
        fail('READER_UNAVAILABLE_IN_NATIVE_STAGE_NAMESPACE')
    print('V6_NATIVE_PDF_READER=PASS', flush=True)
    rc = subprocess.run(
        [*prefix, str(chosen), '-I', '-B', '-c', worker, str(appdir), jobid, str(wheel)],
        cwd=str(appdir), env=env, timeout=480,
    ).returncode
    if rc:
        fail('V6_NATIVE_WORKER_RC_' + str(rc))
    build = v5['get']('/health/build')
    artifact = v5['get']('/health/artifact?deep=true')
    ready = v5['get']('/health/ready')
    if not (build.get('artifact_id') == artifact.get('artifact_id') == v5['ART']
            and artifact.get('files_verified') == 98
            and artifact.get('mismatch_count') == 0
            and ready.get('status') == 'ready'):
        fail('POST_PDF_STAGE_IDENTITY_CHANGED')
    print('POST_QA_STAGE_98_98_READY=PASS', flush=True)
    print('PRODUCTION_NOT_TOUCHED=TRUE', flush=True)
    print('FINAL_RESULT=PDF_STRUCTURE_VERIFIED_VISUAL_QA_PENDING', flush=True)


if __name__ == '__main__':
    main()
