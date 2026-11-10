import base64
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from highzyme.compute.connector import ComputeServer, child_path


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.token = 'foundation-test-only-' + 'x' * 24
        self.server = ComputeServer(('127.0.0.1', 0), Path(self.temp.name), self.token)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        for job in list(self.server.jobs):
            self.server.cancel(job)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, route, body=None, token=True):
        req = Request('http://127.0.0.1:%d%s' % (self.server.server_port, route),
                      data=None if body is None else json.dumps(body).encode(),
                      headers={'Authorization': 'Bearer ' + self.token if token else '', 'Content-Type': 'application/json'})
        with urlopen(req, timeout=5) as response:
            return json.load(response)

    def wait(self, job):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = self.request('/jobs/' + job['id'])
            if result['status'] not in ('queued', 'running'):
                return result
            time.sleep(.05)
        self.fail('Job did not finish')

    def test_authentication_and_capabilities(self):
        with self.assertRaises(HTTPError) as denied:
            self.request('/health', token=False)
        self.assertEqual(denied.exception.code, 401)
        self.assertIn('python', self.request('/health')['capabilities'])

    def test_execute_download_and_no_token_in_job_environment(self):
        script = "import os; from pathlib import Path; assert 'HIGHZYME_COMPUTE_TOKEN' not in os.environ; Path('result.txt').write_text(str(sum(range(11)))); print('done')"
        job = self.request('/jobs', {'script': script, 'capability': 'python'})
        result = self.wait(job)
        self.assertEqual(result['status'], 'completed')
        self.assertIn('done', result['stdout'])
        output = self.request('/jobs/' + job['id'] + '/file?path=result.txt')
        self.assertEqual(base64.b64decode(output['data']), b'55')
        with self.assertRaises(HTTPError):
            self.request('/jobs/' + job['id'] + '/file?path=../outside')

    def test_failure_and_timeout(self):
        failed = self.request('/jobs', {'script': "raise ValueError('expected')"})
        self.assertEqual(self.wait(failed)['status'], 'failed')
        timeout = self.request('/jobs', {'script': 'import time; time.sleep(10)', 'timeout_seconds': 1})
        self.assertEqual(self.wait(timeout)['status'], 'timed_out')

    def test_cancel_is_terminal(self):
        job = self.request('/jobs', {'script': 'import time; time.sleep(20)'})
        self.request('/jobs/' + job['id'] + '/cancel', {})
        self.assertEqual(self.wait(job)['status'], 'cancelled')

    def test_refuse_missing_capability_and_invalid_input_path(self):
        for data in ({'script': 'pass', 'capability': 'not-installed'}, {'script': 'pass', 'files': {'../bad': 'x'}}):
            with self.assertRaises(HTTPError):
                self.request('/jobs', data)
        with self.assertRaises(ValueError):
            child_path(Path(self.temp.name), '../escape')


if __name__ == '__main__':
    unittest.main()
