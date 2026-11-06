import unittest

from media_distill.subtitles import parse_subtitles
from media_distill.transcript import render_transcript

WEBVTT_SAMPLE: str = (
    "WEBVTT\n"
    "Kind: captions\n"
    "Language: en\n"
    "\n"
    "NOTE this is a comment block\n"
    "that spans two lines\n"
    "\n"
    "00:00:01.000 --> 00:00:04.000\n"
    "Hello <b>world</b>\n"
    "\n"
    "00:00:05.000 --> 00:00:08.000\n"
    "Second cue\n"
)

SRT_SAMPLE: str = (
    "1\n"
    "00:00:01,000 --> 00:00:04,000\n"
    "Hello world\n"
    "\n"
    "2\n"
    "00:00:05,000 --> 00:00:08,000\n"
    "Second cue\n"
)


class ParseSubtitlesTests(unittest.TestCase):
    def test_webvtt_with_header_note_and_two_cues(self) -> None:
        result: dict = parse_subtitles(WEBVTT_SAMPLE)
        self.assertEqual(
            result,
            {
                "segments": [
                    {"start": "00:00:01", "text": "Hello world"},
                    {"start": "00:00:05", "text": "Second cue"},
                ]
            },
        )

    def test_srt_with_cue_numbers_and_comma_timestamps(self) -> None:
        result: dict = parse_subtitles(SRT_SAMPLE)
        self.assertEqual(
            result,
            {
                "segments": [
                    {"start": "00:00:01", "text": "Hello world"},
                    {"start": "00:00:05", "text": "Second cue"},
                ]
            },
        )

    def test_inline_markup_stripped_and_whitespace_collapsed(self) -> None:
        text: str = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:03.000\n"
            "<v Speaker><c>word  one</c>  <00:00:01.500><i>word  two</i></v>\n"
        )
        result: dict = parse_subtitles(text)
        self.assertEqual(result["segments"][0]["text"], "word one word two")

    def test_rolling_duplicate_deduplication(self) -> None:
        text: str = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:02.000\n"
            "Hello\n"
            "\n"
            "00:00:02.000 --> 00:00:04.000\n"
            "Hello\n"
            "\n"
            "00:00:04.000 --> 00:00:06.000\n"
            "Hello world\n"
            "\n"
            "00:00:06.000 --> 00:00:08.000\n"
            "Goodbye\n"
        )
        result: dict = parse_subtitles(text)
        self.assertEqual(
            [s["text"] for s in result["segments"]],
            ["Hello", "world", "Goodbye"],
        )

    def test_output_feeds_render_transcript(self) -> None:
        result: dict = parse_subtitles(SRT_SAMPLE)
        md: str = render_transcript(result)
        lines: list[str] = md.strip().splitlines()
        self.assertEqual(lines[0], "# Transcript")
        self.assertEqual(lines[2], "- [00:00:01] Hello world")
        self.assertEqual(lines[3], "- [00:00:05] Second cue")

    def test_no_cues_raises_valueerror(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_subtitles("WEBVTT\n\n")
        self.assertIn("no cues", str(ctx.exception))

    def test_malformed_timing_line_raises_valueerror(self) -> None:
        text: str = (
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:03.000\n"
            "good cue\n"
            "\n"
            "not a timing line\n"
            "some text\n"
        )
        with self.assertRaises(ValueError) as ctx:
            parse_subtitles(text)
        self.assertIn("malformed timing line", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()


class YouTubePlaceholderTests(unittest.TestCase):
    def test_space_only_placeholder_line_does_not_end_the_cue(self) -> None:
        text: str = (
            "WEBVTT\n"
            "Kind: captions\n"
            "\n"
            "00:00:02.760 --> 00:00:04.470 align:start position:0%\n"
            " \n"
            "Il<00:00:02.920><c> bello</c><00:00:03.280><c> della</c>\n"
            "\n"
            "00:00:04.470 --> 00:00:06.750 align:start position:0%\n"
            "programmazione<00:00:05.200><c> automatica</c>\n"
        )
        result: dict = parse_subtitles(text)
        self.assertEqual(
            result,
            {
                "segments": [
                    {"start": "00:00:02", "text": "Il bello della"},
                    {"start": "00:00:04", "text": "programmazione automatica"},
                ]
            },
        )
