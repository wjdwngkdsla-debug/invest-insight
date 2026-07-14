from __future__ import annotations

import unittest

from scripts.management import (
    apply_schedule_correction,
    apply_stock_management,
    build_correction_tasks,
    merge_stock_management,
)


class StockManagementMigrationTest(unittest.TestCase):
    def test_saved_exclusion_wins_without_dropping_existing_data(self) -> None:
        saved = [{
            "scope": "IPO일정", "name": "LS전선", "corp_code": "00683283",
            "management_status": "제외고정", "visibility": "비공개",
        }]
        schedule = {"items": [{
            "corp_code": "00683283", "name": "LS전선", "band_low": 10000,
            "last_rcept_no": "20260101000001", "review_pending": True,
        }], "past_items": [], "history": []}

        rows = merge_stock_management(saved, [], schedule)
        _, applied, seeds = apply_stock_management(rows, [], schedule, today="2026-07-14")

        self.assertEqual(rows[0]["management_status"], "제외고정")
        self.assertTrue(applied["items"][0]["fixed_excluded"])
        self.assertEqual(applied["items"][0]["band_low"], 10000)
        self.assertIn("corp:00683283", applied["fixed_exclusions"])
        self.assertEqual(seeds, [])

    def test_name_only_manual_entry_is_visible_with_unknown_fields(self) -> None:
        rows = [{
            "scope": "IPO일정", "name": "새회사", "management_status": "수동편입",
            "visibility": "노출",
        }]
        _, schedule, seeds = apply_stock_management(rows, [], {"items": [], "past_items": [], "history": []}, today="2026-07-14")

        item = schedule["items"][0]
        self.assertTrue(item["corp_code"].startswith("manual-"))
        self.assertTrue(item["manual_entry"])
        self.assertFalse(item["review_pending"])
        self.assertNotIn("forecast_start", item)
        self.assertEqual(seeds, ["새회사"])

    def test_missing_management_row_does_not_delete_legacy_target(self) -> None:
        targets = [{"name": "기존회사", "code": "123456", "listing_date": "2026-01-01", "market": "코스닥"}]
        rows = merge_stock_management([], targets, {"items": [], "past_items": []})
        applied_targets, _, _ = apply_stock_management(rows, targets, {"items": [], "past_items": [], "history": []})

        self.assertEqual(applied_targets[0]["code"], "123456")

    def test_automatic_review_state_is_not_persisted_as_manual_command(self) -> None:
        schedule = {"items": [{
            "corp_code": "00123456", "name": "자동회사", "review_pending": True,
            "last_rcept_no": "20260714000001",
        }], "past_items": [], "history": []}

        rows = merge_stock_management([], [], schedule)
        _, applied, seeds = apply_stock_management(rows, [], schedule, today="2026-07-14")

        self.assertEqual(rows[0]["management_status"], "자동")
        self.assertEqual(rows[0]["visibility"], "")
        self.assertTrue(applied["items"][0]["review_pending"])
        self.assertNotIn("manual_entry", applied["items"][0])
        self.assertEqual(seeds, [])

    def test_switching_manual_entry_back_to_auto_clears_manual_flags(self) -> None:
        schedule = {"items": [{
            "corp_code": "manual-old", "name": "수동회사", "manual_entry": True,
            "review_approved": True, "review_pending": False,
        }], "past_items": [], "history": []}
        rows = [{
            "scope": "IPO일정", "name": "수동회사", "management_status": "자동",
            "visibility": "",
        }]

        _, applied, seeds = apply_stock_management(rows, [], schedule, today="2026-07-14")

        self.assertNotIn("manual_entry", applied["items"][0])
        self.assertNotIn("review_approved", applied["items"][0])
        self.assertEqual(seeds, ["수동회사"])

    def test_dart_identity_upgrade_does_not_duplicate_name_only_entry(self) -> None:
        saved = [{
            "scope": "IPO일정", "name": "신규회사 임시명", "management_status": "수동편입",
            "visibility": "노출",
        }]
        schedule = {"items": [{
            "corp_code": "00123456", "name": "신규회사", "management_name": "신규회사 임시명",
            "manual_entry": True, "last_rcept_no": "20260714000001",
        }], "past_items": [], "history": []}

        rows = merge_stock_management(saved, [], schedule)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "신규회사")
        self.assertEqual(rows[0]["corp_code"], "00123456")
        self.assertEqual(rows[0]["management_status"], "수동편입")


class CorrectionPrecedenceTest(unittest.TestCase):
    def test_temporary_value_is_not_locked(self) -> None:
        item: dict = {"name": "새회사"}
        changed = apply_schedule_correction(item, {
            "field": "청약일", "manual_value": "2026-08-01 ~ 2026-08-02",
            "override_mode": "임시", "status": "대기",
        })

        self.assertTrue(changed)
        self.assertEqual(item["sub_start"], "2026-08-01")
        self.assertEqual(item["provisional_fields"], ["sub_end", "sub_start"])
        self.assertNotIn("manual_fields", item)

    def test_fixed_value_is_locked(self) -> None:
        item: dict = {"name": "새회사"}
        apply_schedule_correction(item, {
            "field": "확정공모가", "manual_value": "21,500",
            "override_mode": "고정", "status": "대기",
        })

        self.assertEqual(item["final_price"], 21500)
        self.assertEqual(item["manual_fields"], ["final_price"])
        self.assertNotIn("provisional_fields", item)

    def test_changing_temporary_value_to_fixed_is_recorded_as_a_change(self) -> None:
        item: dict = {
            "name": "새회사", "final_price": 21500,
            "provisional_fields": ["final_price"],
        }

        changed = apply_schedule_correction(item, {
            "field": "확정공모가", "manual_value": "21,500",
            "override_mode": "고정", "status": "적용",
        })

        self.assertTrue(changed)
        self.assertEqual(item["manual_fields"], ["final_price"])
        self.assertNotIn("provisional_fields", item)

    def test_temporary_task_becomes_auto_resolved_after_official_value_arrives(self) -> None:
        saved = [{
            "task_id": "schedule:00123456:확정공모가", "target": "IPO일정",
            "name": "새회사", "code": "00123456", "field": "확정공모가",
            "manual_value": "21,500", "override_mode": "임시", "status": "적용",
        }]
        schedule = {"items": [{
            "corp_code": "00123456", "name": "새회사", "final_price": 22000,
            "manual_entry": True,
        }]}

        tasks = build_correction_tasks(saved, [], schedule, [], [], today="2026-07-14")
        row = next(task for task in tasks if task["task_id"] == "schedule:00123456:확정공모가")

        self.assertEqual(row["auto_value"], "22000")
        self.assertEqual(row["manual_value"], "21,500")
        self.assertEqual(row["status"], "자동해결")


if __name__ == "__main__":
    unittest.main()
