import hashlib,unittest
import report_retrieval_timeout_patch as patch

FIXTURE=b'''APP_VERSION = '1.2.124'
RELEASE_REVISION = '1.2.124'
BUILD_SIGNATURE = 'JUDUN_1.2.124_STREAMING_EVIDENCE_SEARCH_20261022'
def unrelated():
    return 'preserve all existing data and report templates'
def serve_search():
    return 'timer=setTimeout(()=>controller.abort(),18000)'
'''
def apply(raw):return patch.transform(raw,expected_sha256=hashlib.sha256(raw).hexdigest())
class RetrievalPatchTests(unittest.TestCase):
    def test_restricted_transform_preserves_every_other_byte(self):
        out=apply(FIXTURE)
        expected=FIXTURE.replace(b"'1.2.124'",b"'1.2.125'").replace(b'JUDUN_1.2.124_STREAMING_EVIDENCE_SEARCH_20261022',b'JUDUN_1.2.125_REPORT_RETRIEVAL_TIMEOUT_20261022').replace(b'controller.abort(),18000',b'controller.abort(),90000')
        self.assertEqual(out,expected)
    def test_unknown_source_is_refused(self):
        with self.assertRaisesRegex(ValueError,'CURRENT_APP_SHA_MISMATCH'):patch.transform(FIXTURE)
    def test_changed_timeout_is_refused(self):
        with self.assertRaisesRegex(ValueError,'RETRIEVAL_TIMEOUT_DRIFT'):apply(FIXTURE.replace(b'18000',b'20000'))
    def test_duplicate_timeout_is_refused(self):
        with self.assertRaisesRegex(ValueError,'RETRIEVAL_TIMEOUT_DRIFT'):apply(FIXTURE.replace(b"18000)'",b"18000);timer=setTimeout(()=>controller.abort(),18000)'"))
    def test_changed_base_version_is_refused(self):
        with self.assertRaisesRegex(ValueError,'RELEASE_METADATA_DRIFT'):apply(FIXTURE.replace(b"'1.2.124'",b"'1.2.123'"))
if __name__=='__main__':unittest.main()
