"""Unit tests: no SigNoz or app network access."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('build_diagnosis', SCRIPTS / 'build_diagnosis.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class DiagnosisTests(unittest.TestCase):
    def test_dedup_hypotheses_and_keep_proof_boundaries(self):
        sample = {
            'summary': {
                'endpoint': 'GET /api/v1/items', 'service':'demo-fastapi',
                'trace_id':'fakeid1','timestamp_utc':'2026-11-18 00:00:00 UTC',
                'latency_ms':8100,'span_count':164,'mongo_count':90,'mongo_find_count':85,
                'mongo_wall_ms':4500,'mongo_sum_ms':4560,'uncovered_ms':2200,
                'uncovered_percent':27.2,'max_self_ms':2200,'max_self_span':'endpoint'
            },
            'groups':[{'category':'MongoDB','operation':'demo.find','count':85,'sum_ms':4300,'wall_union_ms':4210,'max_ms':45}],
            'top_gaps':[{'duration_ms':2200,'start_offset_ms':5800}],
            'repeated_operations':[{'category':'MongoDB','operation':'demo.find','count':85,'sum_ms':4300,'wall_union_ms':4210,'max_ms':45}],
            'truncated_spans':False
        }
        output=mod.build([sample,dict(sample,summary=dict(sample['summary'],trace_id='fakeid2',latency_ms=7900))], Path('analysis.json'))
        self.assertEqual(output['total_slow_request_samples'],2)
        self.assertEqual(output['endpoint_count'],1)
        route=output['endpoints'][0]
        self.assertEqual(route['slow_samples'],2)
        self.assertEqual(route['sample_avg_ms'],8000)
        self.assertEqual(len(route['hypotheses_to_verify']),2)
        self.assertEqual(len(route['hypotheses_to_verify'][0]['observed_trace_ids']),2)
        self.assertFalse(route['source_code_verified'])
        self.assertIn('fakeid1',mod.to_markdown(output))
        self.assertIn('P50/P95/P99', ' '.join(output['limitations']))

    def test_empty_results_and_long_mongo(self):
        empty=mod.build([],Path('analysis.json'))
        self.assertEqual(empty['endpoint_count'],0)
        self.assertIn('根因',mod.to_markdown(empty))
        e={'summary':{'endpoint':'POST /foo','service':'example','trace_id':'abc','latency_ms':6000},'groups':[{'category':'MongoDB','operation':'findAndModify','count':1,'max_ms':2900,'wall_union_ms':2900}], 'truncated_spans':False}
        out=mod.build([e],Path('analysis.json'))
        self.assertEqual(out['endpoints'][0]['hypotheses_to_verify'][0]['id'],'long_mongodb_operation')

    def test_no_required_network(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'analysis.json'
            path.write_text(json.dumps([]),encoding='utf-8')
            self.assertEqual(mod.build(json.loads(path.read_text()),path)['total_slow_request_samples'],0)

if __name__=='__main__': unittest.main()
