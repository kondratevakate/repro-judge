"""Unit tests for protocol 004 edits."""
import unittest

import mutate as M

PAGES = [
    ("pages/index.md", "# Index\n\n| Claim | Verdict |\n|---|---|\n| Claim 1 | verified |\n| Claim 2 | toy |\nC1 holds.\n"),
    ("pages/claim-1-coverage/page.md", "# Claim 1: coverage\n\n* coverage 0.91   \n\n\n\nTable: 0.91 vs 0.90\n"),
    ("pages/claim-2-scale/page.md", "# Claim 2: scale\n\nToy run only.\n"),
    ("pages/claim-10-other/page.md", "# Claim 10\n\nclaim 10 detail\n"),
]


class EditTests(unittest.TestCase):
    def test_unique_page_lookup_does_not_confuse_1_and_10(self):
        self.assertEqual(M.claim_page_index(PAGES, 1), 1)
        self.assertEqual(M.claim_page_index(PAGES, 10), 3)
        self.assertIsNone(M.claim_page_index(PAGES, 3))

    def test_r1_removes_target_evidence_everywhere(self):
        out, rec = M.r1_remove_evidence(PAGES, 1)
        text = "\n".join(t for _, t in out)
        self.assertNotIn("0.91", text)
        self.assertNotIn("C1 holds", text)
        self.assertIn(M.R1_SENTENCE, out[1][1])
        self.assertTrue(out[1][1].startswith("# Claim 1: coverage"))
        self.assertIn("Claim 2 | toy", text)          # other claims untouched
        self.assertIn("claim 10 detail", text)        # claim 10 not matched by claim 1
        self.assertEqual(rec["lines_deleted_elsewhere"], 2)

    def test_i1_preserves_words(self):
        out, rec = M.i1_reformat(PAGES, 1)
        self.assertEqual(out[1][1].split(), PAGES[1][1].replace("*", "-").split())
        self.assertFalse(rec["identical"])
        self.assertEqual(out[0], PAGES[0])

    def test_i3_adds_only_the_paragraph(self):
        out, _ = M.i3_inflate(PAGES, 2)
        self.assertEqual(out[2][1].replace(M.I3_PARAGRAPH + "\n\n", ""), PAGES[2][1])
        self.assertEqual([p for k, p in enumerate(out) if k != 2], [p for k, p in enumerate(PAGES) if k != 2])

    def test_missing_page_raises(self):
        with self.assertRaises(ValueError):
            M.r1_remove_evidence(PAGES, 3)


if __name__ == "__main__":
    unittest.main()
