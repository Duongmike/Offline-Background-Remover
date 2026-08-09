from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from image_tool.localization import EN, VI, LocalizationService, validate_translations
from image_tool.settings import JsonSettingsRepository


class LocalizationTests(unittest.TestCase):
    def test_locales_have_matching_keys_and_placeholders(self) -> None:
        validate_translations()
        self.assertEqual(set(EN), set(VI))

    def test_english_and_vietnamese_primary_actions(self) -> None:
        service = LocalizationService("en")
        self.assertEqual("START PROCESSING", service.text("action.run"))
        service.set_language("vi")
        self.assertEqual("BẮT ĐẦU XỬ LÝ", service.text("action.run"))

    def test_unknown_language_falls_back_to_vietnamese(self) -> None:
        service = LocalizationService("unsupported")
        self.assertEqual("vi", service.language)


class SettingsRepositoryTests(unittest.TestCase):
    def test_settings_round_trip_unicode_and_language(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nested" / "settings.json"
            repository = JsonSettingsRepository(path, Path(temporary) / "legacy.json")
            repository.save({"language": "en", "input": "D:/Ảnh thử"})
            self.assertEqual({"language": "en", "input": "D:/Ảnh thử"}, repository.load())
            self.assertEqual("en", json.loads(path.read_text(encoding="utf-8"))["language"])
            self.assertFalse(any(path.parent.glob("*.tmp")))

    def test_legacy_settings_are_loaded_when_current_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy = root / "legacy.json"
            legacy.write_text('{"input_mode": "Cả folder"}', encoding="utf-8")
            repository = JsonSettingsRepository(root / "new" / "settings.json", legacy)
            self.assertEqual("Cả folder", repository.load()["input_mode"])


if __name__ == "__main__":
    unittest.main()
