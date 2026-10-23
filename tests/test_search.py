import json
import subprocess
import unittest
from unittest.mock import patch

from queryfi.search import SearchError, SearchQuery, SearchResult
from queryfi.searxncrawl import SearxNCrawlSearch, SearchSettings


class SearchQueryTests(unittest.TestCase):
    def test_query_is_trimmed_and_rejects_blank_overlong_and_null_text(self):
        self.assertEqual(SearchQuery("  Python tutorials  ").value, "Python tutorials")
        for value in ("  ", "x" * 501, "python\0tutorial"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                SearchQuery(value)


class SearxNCrawlTests(unittest.TestCase):
    def setUp(self):
        self.settings = SearchSettings(timeout=45)
        self.environment = {"SEARXNG_URL": "http://localhost:8888", "YDC_API_KEY": "private-key"}
        self.search = SearxNCrawlSearch(self.settings, self.environment)
        run_patch = patch("queryfi.searxncrawl.subprocess.run")
        self.run = run_patch.start()
        self.addCleanup(run_patch.stop)
        self.run.return_value = subprocess.CompletedProcess([], 0, json.dumps({"results": [{
            "title": "Python tutorial", "url": "https://docs.python.org/3/tutorial/",
            "content": "Learn Python", "providers": ["searxng", "youcom"],
        }]}), "")

    def test_search_uses_documented_json_cli_and_preserves_provider_attribution(self):
        results = self.search.search(SearchQuery("Python tutorials"))
        self.assertEqual(results, (SearchResult("Python tutorial", "https://docs.python.org/3/tutorial/",
                                                "Learn Python", ("searxng", "youcom")),))
        command = self.run.call_args.args[0]
        self.assertEqual(command, ["uvx", "--from", "searxncrawl==0.32.0", "search",
                                   "--json", "--max-results", "5", "--", "Python tutorials"])
        options = self.run.call_args.kwargs
        self.assertEqual(options["timeout"], 45)
        self.assertFalse(options["shell"])
        self.assertEqual(options["encoding"], "utf-8")
        self.assertEqual(options["env"]["YDC_API_KEY"], "private-key")
        self.assertEqual(options["env"]["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(options["env"]["SEARCH_RESULT_FIELDS"], "title,url,content,providers")
        self.assertNotIn("private-key", " ".join(command))

    def test_query_cannot_be_interpreted_as_cli_flags_or_shell_code(self):
        query = '--output stolen.json; $(echo unsafe) "quoted"'
        self.search.search(SearchQuery(query))
        self.assertEqual(self.run.call_args.args[0][-2:], ["--", query])

    def test_empty_results_are_distinct_from_failure(self):
        self.run.return_value.stdout = '{"results": []}'
        self.assertEqual(self.search.search(SearchQuery("unusual query")), ())

    def test_missing_provider_fails_before_launching_cli(self):
        for environment in ({}, {"SEARXNG_URL": " ", "YDC_API_KEY": " "}):
            with self.subTest(environment=environment), self.assertRaisesRegex(SearchError, "not configured"):
                SearxNCrawlSearch(self.settings, environment).search(SearchQuery("Python"))
        self.run.assert_not_called()

    def test_either_provider_can_be_used_independently(self):
        for environment in ({"SEARXNG_URL": "http://localhost:8888"}, {"YDC_API_KEY": "key"}):
            with self.subTest(environment=environment):
                self.assertTrue(SearxNCrawlSearch(self.settings, environment).search(SearchQuery("Python")))
                child_environment = self.run.call_args.kwargs["env"]
                for name in ("SEARXNG_URL", "YDC_API_KEY"):
                    self.assertEqual(child_environment[name], environment.get(name, ""))

    def test_process_failures_have_safe_actionable_messages(self):
        for error, expected in ((FileNotFoundError("private path"), "uv"),
                                (subprocess.TimeoutExpired("private command", 45), "timed out"),
                                (OSError("private path"), "could not start")):
            self.run.side_effect = error
            with self.subTest(error=error), self.assertRaisesRegex(SearchError, expected) as caught:
                self.search.search(SearchQuery("Python"))
            self.assertNotIn("private", str(caught.exception))

    def test_nonzero_exit_does_not_leak_provider_credentials(self):
        self.run.return_value.returncode = 1
        self.run.return_value.stderr = "private-key: provider failed"
        with self.assertRaisesRegex(SearchError, "could not search") as caught:
            self.search.search(SearchQuery("Python"))
        self.assertNotIn("private-key", str(caught.exception))

    def test_malformed_or_error_responses_are_not_reported_as_no_results(self):
        for payload in ("not json", "null", "[]", "{}", '{"error": "secret"}',
                        '{"results": {}}', '{"results": [null]}', '{"results": [{}]}',
                        '{"results": [{"url": "javascript:alert(1)"}]}'):
            self.run.return_value.stdout = payload
            with self.subTest(payload=payload), self.assertRaises(SearchError):
                self.search.search(SearchQuery("Python"))

    def test_optional_fields_and_unicode_are_supported(self):
        self.run.return_value.stdout = json.dumps({"results": [{"url": "https://example.org/",
                                                               "title": "Știință 日本語"}]})
        result, = self.search.search(SearchQuery("știință"))
        self.assertEqual(result.title, "Știință 日本語")
        self.assertEqual(result.snippet, "")
        self.assertEqual(result.providers, ())

    def test_settings_reject_non_finite_non_positive_and_excessive_timeouts(self):
        for timeout in (0, -1, float("nan"), float("inf"), 601):
            with self.subTest(timeout=timeout), self.assertRaisesRegex(ValueError, "SEARXNCRAWL_TIMEOUT"):
                SearchSettings(timeout=timeout)
