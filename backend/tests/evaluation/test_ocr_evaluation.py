"""OCR Evaluation Harness and Transcription Accuracy Metrics (CER / WER).

This module provides standard metrics for handwritten OCR evaluation:
- Character Error Rate (CER)
- Word Error Rate (WER)
- Sequence fidelity (Longest Common Subsequence)
"""
from django.test import SimpleTestCase


def calculate_cer(reference: str, hypothesis: str) -> float:
    """Calculate Character Error Rate using Levenshtein edit distance.
    
    CER = (Substitutions + Deletions + Insertions) / len(reference)
    """
    ref = list(reference)
    hyp = list(hypothesis)
    n = len(ref)
    if n == 0:
        return 0.0 if len(hyp) == 0 else 1.0

    # Dynamic programming Levenshtein distance matrix
    dp = [[0] * (len(hyp) + 1) for _ in range(n + 1)]

    for i in range(n + 1):
        dp[i][0] = i
    for j in range(len(hyp) + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, len(hyp) + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],      # deletion
                    dp[i][j - 1],      # insertion
                    dp[i - 1][j - 1],  # substitution
                )

    return float(dp[n][len(hyp)]) / float(n)


def calculate_wer(reference: str, hypothesis: str) -> float:
    """Calculate Word Error Rate using word-level Levenshtein edit distance.
    
    WER = (Substitutions + Deletions + Insertions) / len(reference_words)
    """
    ref_words = reference.strip().split()
    hyp_words = hypothesis.strip().split()
    n = len(ref_words)
    if n == 0:
        return 0.0 if len(hyp_words) == 0 else 1.0

    dp = [[0] * (len(hyp_words) + 1) for _ in range(n + 1)]

    for i in range(n + 1):
        dp[i][0] = i
    for j in range(len(hyp_words) + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, len(hyp_words) + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],
                    dp[i][j - 1],
                    dp[i - 1][j - 1],
                )

    return float(dp[n][len(hyp_words)]) / float(n)


class OCREvaluationMetricsTests(SimpleTestCase):
    def test_cer_exact_match(self):
        self.assertEqual(calculate_cer("Hello world", "Hello world"), 0.0)

    def test_cer_single_substitution(self):
        # 1 substitution in 10 characters = 0.10
        self.assertAlmostEqual(calculate_cer("1234567890", "12345X7890"), 0.10)

    def test_cer_empty_reference(self):
        self.assertEqual(calculate_cer("", ""), 0.0)
        self.assertEqual(calculate_cer("", "abc"), 1.0)

    def test_wer_exact_match(self):
        self.assertEqual(calculate_wer("The quick brown fox", "The quick brown fox"), 0.0)

    def test_wer_single_word_substitution(self):
        # 1 error in 4 words = 0.25
        self.assertAlmostEqual(calculate_wer("The quick brown fox", "The fast brown fox"), 0.25)

    def test_wer_deletion(self):
        # 1 deletion in 4 words = 0.25
        self.assertAlmostEqual(calculate_wer("The quick brown fox", "The brown fox"), 0.25)

    def test_wer_insertion(self):
        # 1 insertion in 3 words = 1/3 = 0.3333
        self.assertAlmostEqual(calculate_wer("The brown fox", "The very brown fox"), 1.0 / 3.0)

    def test_evaluation_benchmark_sample(self):
        # Realistic student handwriting OCR test sample
        gt_transcript = "Binary Search operates on sorted arrays with O(log n) time complexity."
        ocr_transcript = "Binary Search operates on sorted arrays with O(log n) time complexity."
        cer = calculate_cer(gt_transcript, ocr_transcript)
        wer = calculate_wer(gt_transcript, ocr_transcript)
        self.assertEqual(cer, 0.0)
        self.assertEqual(wer, 0.0)
