import copy
import unittest
from unittest.mock import patch

from scripts.audit_ipo_quality import attempt_repair, merge_tiers, retry_targets
from scripts.ipo_repair_memory import (MAX_CASES, MAX_EXCERPT, capture_case,
    remember_attempt, replay_cases, resolve_cases, retry_due, protect_candidate)
from scripts.ipo_quality import PERIODS, quality_gaps


def valid_item():
    return {'corp_code': '12345678', 'stock_code': '123456', 'name': 'Fixture',
            'market': '코스닥', 'band_low': 1000, 'band_high': 2000, 'offer_shares': 100,
            'initial_shares': 1000, 'underwriter': 'Fixture', 'final_price': 1500,
            'forecast_end': '2026-09-01', 'sub_end': '2026-09-05', 'listing_date': '2026-09-08',
            'demand_ratio': 100, 'sub_ratio': 200, 'last_rcept_no': 'offering', 'report_rcp': 'result',
            'commit_apply': [{'period': p, 'qty': 20} for p in PERIODS],
            'commit_alloc': [{'period': p, 'qty': 10} for p in PERIODS],
            'result_source_check': {'status': 'verified'},
            'holder_lockup': {'status': 'verified', 'rcept_no': 'offering', 'coverage': 'full',
                'total': 500, 'rows': [{'period': '1개월', 'qty': 500}],
                'cumulative_rows': [{'period': '상장일', 'cumulative_float': 500},
                                    {'period': '1개월', 'cumulative_float': 1000}]}}


class RepairMemoryTests(unittest.TestCase):
    def test_partial_merge_preserves_absent_known_and_fixed_tiers(self):
        item = valid_item()
        item['manual_commit_alloc'] = {'6개월': {'qty': 12, 'locked': True}}
        merge_tiers(item, 'commit_alloc', [{'period': '1개월', 'qty': 15},
                    {'period': '3개월', 'qty': None}], 'new')
        tiers = {r['period']: r for r in item['commit_alloc']}
        self.assertEqual(len(tiers), 5)
        self.assertEqual(tiers['1개월']['qty'], 15)
        self.assertEqual(tiers['3개월']['qty'], 10)
        self.assertEqual(tiers['6개월']['qty'], 12)
        self.assertEqual(tiers['6개월']['source'], 'manual_fixed')
        self.assertNotIn('rcept_no', tiers['3개월'])

    def test_regressive_candidate_does_not_replace_good_values(self):
        item = valid_item()
        original = copy.deepcopy(item)
        def repair(candidate, today, artifacts):
            candidate['commit_alloc'][0]['qty'] = 100000
        with patch('scripts.audit_ipo_quality.repair_item', side_effect=repair):
            outcome, reasons = attempt_repair(item, '2026-09-26', 'v1', {'cases': {}})
        self.assertEqual(outcome, 'rejected')
        self.assertTrue(reasons)
        self.assertEqual(item['commit_alloc'], original['commit_alloc'])
        self.assertIn('quality_refresh_error', item)
        self.assertEqual(item['quality_repair_state']['outcome'], 'rejected')

    def test_incomplete_new_result_cannot_be_hidden_by_old_complete_tiers(self):
        old = valid_item()
        new = copy.deepcopy(old)
        new['result_source_check']['status'] = 'parse_incomplete'
        self.assertTrue(protect_candidate(old, new, '2026-09-26'))

    def test_rejected_full_parse_records_evidence_without_replacing_values(self):
        item = valid_item()
        memory = {'cases': {}}
        def repair(candidate, today, artifacts):
            candidate['holder_lockup'] = {'status': 'review', 'rcept_no': 'new', 'reason': 'unknown period'}
            artifacts.append({'receipt': 'new', 'kind': 'holders', 'reason': 'unknown period',
                              'document': '<TABLE><TR><TD>유통가능</TD></TR></TABLE>', 'table_index': 1})
        with patch('scripts.audit_ipo_quality.repair_item', side_effect=repair):
            outcome, _ = attempt_repair(item, '2026-09-26', 'v1', memory)
        self.assertEqual(outcome, 'rejected')
        self.assertEqual(item['holder_lockup']['total'], 500)
        self.assertEqual(len(memory['cases']), 1)
        case = next(iter(memory['cases'].values()))
        self.assertEqual(case['receipt'], 'new')
        self.assertEqual(case['status'], 'unresolved')

    def test_transient_errors_do_not_get_week_long_delay_and_history_is_bounded(self):
        item = valid_item()
        for _ in range(9):
            remember_attempt(item, '2026-09-26', 'v1', 'source_error', ['503'])
        self.assertEqual(item['quality_repair_state']['next_retry'], '2026-09-27')
        self.assertEqual(len(item['quality_repair_state']['history']), 5)

    def test_source_failure_is_transactional(self):
        item = valid_item()
        def repair(candidate, today, artifacts):
            candidate['final_price'] = 0
            raise RuntimeError('source unavailable')
        with patch('scripts.audit_ipo_quality.repair_item', side_effect=repair):
            outcome, _ = attempt_repair(item, '2026-09-26', 'v1', {'cases': {}})
        self.assertEqual(outcome, 'source_error')
        self.assertEqual(item['final_price'], 1500)

    def test_success_is_not_an_exception_free_but_invalid_parse(self):
        item = valid_item()
        item['commit_apply'] = []
        with patch('scripts.audit_ipo_quality.repair_item'):
            outcome, _ = attempt_repair(item, '2026-09-26', 'v1', {'cases': {}})
        self.assertEqual(outcome, 'unresolved')

    def test_recovery_clears_error_and_closes_exact_receipt_case(self):
        item = valid_item()
        item['quality_refresh_error'] = {'message': 'old'}
        memory = {'cases': {'a': {'corp_code': '12345678', 'kind': 'holders',
                                 'receipt': 'offering', 'status': 'unresolved'},
                            'b': {'corp_code': '12345678', 'kind': 'holders',
                                 'receipt': 'other', 'status': 'unresolved'}}}
        def repair(candidate, today, artifacts):
            candidate.pop('quality_refresh_error', None)
        with patch('scripts.audit_ipo_quality.repair_item', side_effect=repair):
            outcome, _ = attempt_repair(item, '2026-09-26', 'v1', memory)
        self.assertEqual(outcome, 'verified')
        self.assertEqual(quality_gaps(item, today='2026-09-26'), [])
        self.assertEqual(memory['cases']['a']['status'], 'resolved')
        self.assertEqual(memory['cases']['b']['status'], 'unresolved')

    def test_repeated_failure_backs_off_and_source_or_parser_change_bypasses(self):
        item = valid_item()
        for today, expected in [('2026-09-26', '2026-09-27'), ('2026-09-27', '2026-09-29'),
                                ('2026-09-29', '2026-10-03'), ('2026-10-03', '2026-10-10')]:
            remember_attempt(item, today, 'v1', 'unresolved', ['unknown period'])
            self.assertEqual(item['quality_repair_state']['next_retry'], expected)
        self.assertFalse(retry_due(item, '2026-10-04', 'v1'))
        self.assertTrue(retry_due(item, '2026-10-04', 'v2'))
        item['last_rcept_no'] = 'new correction'
        self.assertTrue(retry_due(item, '2026-10-04', 'v1'))
        remember_attempt(item, '2026-10-04', 'v1', 'unresolved', ['unknown period'])
        self.assertEqual(item['quality_repair_state']['consecutive_attempts'], 1)

    def test_old_empty_arrays_are_retryable_and_errors_prioritized(self):
        healthy = valid_item()
        broken = valid_item()
        broken.update(corp_code='87654321', listing_date='2024-01-01', commit_apply=[], commit_alloc=[])
        chosen = retry_targets([healthy, broken], '2026-09-26', revision='v1')
        self.assertEqual(chosen[0]['corp_code'], '87654321')

    def test_failure_capture_is_bounded_deduplicated_and_only_a_probe(self):
        memory = {'cases': {}}
        doc = '<TABLE><TR><TD>유통가능</TD></TR></TABLE>'
        item = valid_item()
        key = capture_case(memory, item, 'offering', 'holders', 'unknown period', doc, '2026-09-26', 'v1', 1)
        capture_case(memory, item, 'offering', 'holders', 'unknown period', doc, '2026-09-27', 'v1', 1)
        self.assertEqual(len(memory['cases']), 1)
        self.assertEqual(memory['cases'][key]['observations'], 2)
        with patch('scripts.sources.dart_api.holder_snapshot', return_value={'status': 'verified'}):
            replay_cases(memory, 'v2')
        self.assertEqual(memory['cases'][key]['probe'], 'full_document_recheck')
        self.assertEqual(memory['cases'][key]['status'], 'unresolved')
        self.assertEqual(item, valid_item())

    def test_oversized_or_missing_evidence_requires_full_source(self):
        memory = {'cases': {}}
        key = capture_case(memory, valid_item(), 'receipt', 'holders', 'x',
                           '<TABLE>유통가능' + 'x' * MAX_EXCERPT + '</TABLE>', '2026-09-26', 'v1', 1)
        replay_cases(memory, 'v2')
        self.assertEqual(len(memory['cases'][key]['excerpt']), MAX_EXCERPT)
        self.assertEqual(memory['cases'][key]['probe'], 'full_document_required')
        for n in range(MAX_CASES + 2):
            capture_case(memory, valid_item(), str(n), 'holders', 'missing', '', '2026-09-26', 'v1')
        self.assertEqual(len(memory['cases']), MAX_CASES)
        self.assertGreater(memory['evicted_cases'], 0)


if __name__ == '__main__':
    unittest.main()
