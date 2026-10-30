import argparse
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('daily_state', ROOT / 'scripts/daily_state.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class Checks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'private.json'
        self.cfg = m.read_json(ROOT / 'config.json')
    def args(self, **kw):
        a = dict(ward=None,beds=None,add_source=None,remove_source=None,start_hour=None,exclude_note=None,data_root=None)
        a.update(kw)
        return argparse.Namespace(**a)
    def bound(self):
        m.bind(self.cfg,self.path,self.args(ward='虚构单元',beds='2,4',add_source=['test@chatroom|测试群']))
        return m.resolve_paths(m.read_json(self.path))
    def test_unbound(self):
        self.assertEqual(len(m.binding_report(self.cfg)),3)
    def test_bind_does_not_mutate_template(self):
        original = copy.deepcopy(self.cfg)
        self.bound()
        self.assertEqual(self.cfg,original)
    def test_partial(self):
        r=m.bind(self.cfg,self.path,self.args(ward='虚构'))
        self.assertEqual(r['status'],'unbound')
    def test_zero_bed_rejected(self):
        with self.assertRaises(ValueError):m.bind(self.cfg,self.path,self.args(beds='0'))
        self.assertFalse(self.path.exists())
    def test_duplicate_name_not_saved(self):
        with self.assertRaises(ValueError):
            m.bind(self.cfg,self.path,self.args(add_source=['a|相同','b|相同']))
        self.assertFalse(self.path.exists())
    def test_bad_source_type(self):
        self.cfg['sources']=['wrong']
        with self.assertRaises(ValueError):m.binding_report(self.cfg)
    def test_newline_name(self):
        with self.assertRaises(ValueError):m.bind(self.cfg,self.path,self.args(add_source=['a|测试\n错误']))
    def test_shared_template_protected(self):
        with self.assertRaises(ValueError):m.bind(self.cfg,m.TEMPLATE_CONFIG,self.args(ward='虚构'))
    def test_defaults(self):
        cfg=m.resolve_paths(self.cfg)
        self.assertTrue(Path(cfg['paths']['py']).is_file())
        self.assertIn(str(Path.home()),cfg['paths']['reports'])
    def test_missing_data_root(self):
        with self.assertRaises(ValueError):m.check_paths(m.resolve_paths(self.cfg))
    def test_boundary_and_catchup(self):
        cfg=self.bound()
        cfg['paths']['reports']=self.tmp.name
        for time,status in [('06:59:59','not_due'),('07:00:00','due'),('23:59:59','due')]:
            job=m.plan(cfg,datetime.fromisoformat('2026-10-30T'+time+'+08:00'))
            self.assertEqual(job['status'],status)
            self.assertEqual(job['since'],'2026-10-29 07:00')
    def test_corrupt_receipt(self):
        cfg=self.bound(); cfg['paths']['reports']=self.tmp.name
        now=datetime.fromisoformat('2026-10-30T08:00:00+08:00')
        job=m.plan(cfg,now)
        Path(job['receipt']).write_text('{broken',encoding='utf-8')
        self.assertEqual(m.plan(cfg,now)['status'],'due')
    def test_source_failure(self):
        status=m.source_status('\n## 本次读取状态\n- 测试：**读取失败**\n',[{'name':'测试','wxid':'test'}])
        self.assertFalse(status['test'])
    def test_ward_changes_fingerprint(self):
        cfg=self.bound(); before=m.fingerprint(cfg); cfg['ward']='另一个虚构单元'
        self.assertNotEqual(before,m.fingerprint(cfg))
    def test_future_rejected(self):
        with self.assertRaises(ValueError):m.plan(self.bound(),datetime.fromisoformat('2026-10-30T08:00:00+08:00'),'2026-10-30')

if __name__ == '__main__':unittest.main()
