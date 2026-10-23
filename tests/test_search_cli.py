"""Opt-in contract test for the installed CLI; no public search provider is used."""

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from queryfi.search import SearchQuery
from queryfi.searxncrawl import SearchSettings, SearxNCrawlSearch


@unittest.skipUnless(os.environ.get("QUERYFI_CLI_TEST") == "1", "Set QUERYFI_CLI_TEST=1 to run the real searxNcrawl CLI")
class SearchCliTests(unittest.TestCase):
    def test_real_cli_forwards_query_limits_results_and_attributes_provider(self):
        requests = []

        class Provider(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(urlsplit(self.path))
                body = json.dumps({"results": [
                    {"title": f"Știință {index}", "url": f"https://example.org/{index}", "content": "日本語"}
                    for index in range(7)
                ]}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        environment = {**os.environ, "SEARXNG_URL": f"http://127.0.0.1:{server.server_port}",
                       "YDC_API_KEY": "", "SEARXNG_USERNAME": "", "SEARXNG_PASSWORD": "",
                       "NO_PROXY": "127.0.0.1,localhost"}
        query = SearchQuery('--output test.json "știință" & 日本語')

        results = SearxNCrawlSearch(SearchSettings(), environment).search(query)

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].path, "/search")
        parameters = parse_qs(requests[0].query)
        self.assertEqual(parameters["q"], [query.value])
        self.assertEqual(parameters["format"], ["json"])
        self.assertEqual(len(results), 5)
        self.assertEqual(results[0].title, "Știință 0")
        self.assertEqual(results[0].snippet, "日本語")
        self.assertTrue(all(result.providers == ("searxng",) for result in results))
