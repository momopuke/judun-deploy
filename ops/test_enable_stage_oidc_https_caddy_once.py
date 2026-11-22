"""Offline Caddy origin isolation tests; never docker exec or touch production."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "caddy_oidc_oneclick", ROOT / "enable_stage_oidc_https_caddy_once.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def docker_obj(net="host", caddyfile="/tmp/secret-test/Caddyfile", rw=True):
    return {
        "Id": "a" * 64, "Name": "/caddy",
        "State": {"Running": True},
        "Config": {"Image": "caddy:2.9"},
        "HostConfig": {"NetworkMode": net},
        "Mounts": [{
            "Type": "bind", "RW": rw,
            "Destination": "/etc/caddy/Caddyfile", "Source": caddyfile,
        }],
    }


class CaddyBridgeSafetyTests(unittest.TestCase):
    def test_dedicated_host_not_existing_production(self):
        self.assertNotEqual(
            installer.HOST, "judun.142-93-91-214.sslip.io")
        self.assertNotIn(
            b"judun.142-93-91-214.sslip.io {", installer.BLOCK)
        self.assertIn(b"judun-oidc.142-93-91-214.sslip.io {", installer.BLOCK)
        self.assertIn(b"reverse_proxy 127.0.0.1:18762", installer.BLOCK)
        self.assertIn(b"method GET", installer.BLOCK)
        self.assertIn(b"respond \"Forbidden\" 403", installer.BLOCK)

    def test_reject_bridge_and_ro_directory_but_allow_ro_file_mount(self):
        self.assertEqual(installer.candidate_caddies([docker_obj(net="bridge")]), [])
        # Observed VPS topology: stripchat-gateway, host network, read-only
        # single-file bind of /root/stripchat-gateway/Caddyfile.
        ro = docker_obj(caddyfile="/root/stripchat-gateway/Caddyfile", rw=False)
        ro["Name"] = "/stripchat-gateway"
        ro["Config"]["Image"] = "caddy:2-alpine"
        self.assertEqual(installer.candidate_caddies([ro]), [(
            "a" * 64, Path("/root/stripchat-gateway/Caddyfile"), True)])
        directory = docker_obj(rw=False)
        directory["Mounts"][0]["Destination"] = "/etc/caddy"
        self.assertEqual(installer.candidate_caddies([directory]), [])
        self.assertEqual(len(installer.candidate_caddies([docker_obj()])), 1)

    def test_reject_extra_caddy_instances_and_non_running(self):
        objs = [docker_obj(), docker_obj()]
        self.assertEqual(len(installer.candidate_caddies(objs)), 2)
        obj = docker_obj()
        obj["State"]["Running"] = False
        self.assertEqual(installer.candidate_caddies([obj]), [])

    def test_subdirectory_mount_mapped_to_real_caddyfile(self):
        obj = docker_obj()
        obj["Mounts"] = [{
            "Type": "bind", "RW": True,
            "Destination": "/etc/caddy", "Source": "/root/caddy-test",
        }]
        self.assertEqual(
            installer.candidate_caddies([obj])[0][1],
            Path("/root/caddy-test/Caddyfile"))

    def test_nonexistent_admin_and_payment_routes_cannot_be_proxied(self):
        self.assertNotIn(b"/admin", installer.BLOCK)
        self.assertNotIn(b"/payment", installer.BLOCK)
        self.assertIn(b"/__jd_stage_health/v1/health/artifact", installer.BLOCK)
        self.assertNotIn(b"reverse_proxy 127.0.0.1:8011", installer.BLOCK)

    def test_atomic_replace_is_isolated_to_new_file_and_preserves_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Caddyfile"
            source.write_bytes(b"judun.142-93-91-214.sslip.io {\n reverse_proxy 127.0.0.1:8888\n}\n")
            original = source.read_bytes()
            st = source.stat()
            installer.write_caddy_config(
                source, original + installer.BLOCK,
                0o600, st.st_uid, st.st_gid)
            self.assertTrue(source.read_bytes().startswith(original))
            self.assertTrue(source.read_bytes().endswith(installer.BLOCK))
            self.assertEqual(source.stat().st_mode & 0o777, 0o600)
            installer.write_caddy_config(source, original, 0o600, st.st_uid, st.st_gid)
            self.assertEqual(source.read_bytes(), original)

    def test_readonly_docker_bind_host_source_is_inode_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Caddyfile"
            old = b"original host Caddyfile\n"
            source.write_bytes(old)
            obj = docker_obj(caddyfile=str(source), rw=False)
            selected = installer.candidate_caddies([obj])
            self.assertEqual(selected, [("a" * 64, source, True)])
            before_inode = source.stat().st_ino
            st = source.stat()
            installer.write_caddy_config(source, old + installer.BLOCK,
                0o600, st.st_uid, st.st_gid, file_bind=selected[0][2])
            self.assertEqual(source.stat().st_ino, before_inode)
            self.assertTrue(source.read_bytes().endswith(installer.BLOCK))
            installer.write_caddy_config(source, old,
                0o600, st.st_uid, st.st_gid, file_bind=True)
            self.assertEqual(source.read_bytes(), old)
            self.assertEqual(source.stat().st_ino, before_inode)

    def test_single_file_docker_bind_keeps_original_inode(self):
        # A bind of /etc/caddy/Caddyfile pins the host file's inode; replacing
        # it would NOT update what Docker's Caddy process sees.
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Caddyfile"
            original = b"old safe Caddyfile\n"
            source.write_bytes(original)
            st = source.stat()
            installer.write_caddy_config(
                source, original + installer.BLOCK,
                0o600, st.st_uid, st.st_gid, file_bind=True)
            self.assertEqual(source.stat().st_ino, st.st_ino)
            self.assertTrue(source.read_bytes().endswith(installer.BLOCK))
            installer.write_caddy_config(
                source, original, 0o600, st.st_uid, st.st_gid, file_bind=True)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(source.stat().st_ino, st.st_ino)

    def test_never_reload_stale_on_disk_caddyfile_over_live_routes(self):
        class Reply:
            status = 200
            def __init__(self, raw):
                self.raw = raw
            def read(self, size):
                return self.raw
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        class Transport:
            def __init__(self, raw):
                self.raw = raw
            def open(self, request, timeout):
                self.asserted_url = request.full_url
                return Reply(self.raw)
        runtime = Transport(b'{"apps":{"http":{"servers":{"srv0":{"routes":[1]}}}}}')
        with (mock.patch.object(installer, "checked", return_value='{"apps":{"http":{"servers":{"srv0":{"routes":[1]}}}}}'),
              mock.patch.object(installer, "no_proxy", return_value=runtime)):
            self.assertTrue(installer.confirm_running_config_matches_caddyfile("synthetic-id"))
        different = Transport(b'{"apps":{"http":{"servers":{"srv0":{"routes":[2]}}}}}')
        with (mock.patch.object(installer, "checked", return_value='{"apps":{"http":{"servers":{"srv0":{"routes":[1]}}}}}'),
              mock.patch.object(installer, "no_proxy", return_value=different)):
            with self.assertRaisesRegex(installer.Stop, "CADDYFILE_DIFFERS_FROM_RUNNING_CONFIG"):
                installer.confirm_running_config_matches_caddyfile("synthetic-id")

    def test_public_probe_refuses_http_200_leak(self):
        with mock.patch.object(installer, "response_code",
                               return_value=(200, b"should-not-be-public")):
            with self.assertRaisesRegex(installer.Stop,
                                        "PUBLIC_UNAUTHENTICATED_HEALTH_LEAK"):
                installer.public_probe()

    def test_public_probe_allows_only_explicit_403(self):
        with mock.patch.object(installer, "response_code",
                               return_value=(403, b"")):
            self.assertTrue(installer.public_probe())

    def test_apply_requires_explicit_flag(self):
        with mock.patch("sys.argv", ["program"]):
            with self.assertRaisesRegex(installer.Stop, "EXPLICIT_APPLY_REQUIRED"):
                installer.main()


if __name__ == "__main__":
    unittest.main()
