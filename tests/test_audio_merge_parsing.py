import unittest


class AudioMergeParsingTests(unittest.TestCase):
    def test_parse_serialized_list_handles_np_float64_wrappers(self):
        from core._11_merge_audio import _parse_serialized_list

        parsed = _parse_serialized_list(
            "[[np.float64(108.174), np.float64(112.634)]]"
        )

        self.assertEqual(parsed, [[108.174, 112.634]])


if __name__ == "__main__":
    unittest.main()
