import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from sandbox.snapshots import SnapshotError, SnapshotStore

COMPAT={'firecracker':'1.17.0','kernel_sha256':'a'*64,'architecture':'x86_64'}
POLICY={'version':'1.0.0','memory_mib':128,'vcpu_count':1}

class Snapshots(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.store=SnapshotStore(self.root/'store'); self.disk=self.root/'disk'; self.disk.write_bytes(b'coherent disk marker')
    def tearDown(self):
        for folder,dirs,files in os.walk(self.root):
            os.chmod(folder,0o700)
            for name in files: os.chmod(Path(folder)/name,0o600)
        self.tmp.cleanup()
    def capture(self,state,memory): state.write_bytes(b'machine state'); memory.write_bytes(b'memory state')
    def publish(self,interrupt=None): return self.store.publish('s1','tenant-a','session-a',COMPAT,POLICY,self.disk,self.capture,interrupt)
    def validate(self,**changes):
        args=dict(snapshot_id='s1',tenant='tenant-a',session='session-a',compatibility=COMPAT,policy=POLICY); args.update(changes)
        return self.store.validate(**args)
    def test_complete_and_private_restore(self):
        self.publish(); before=self.validate()
        state,memory=self.store.restore_copies('s1','tenant-a','session-a',COMPAT,POLICY,self.root/'restore',self.root/'private-disk')
        memory.write_bytes(b'restored VM writes'); (self.root/'private-disk').write_bytes(b'private changes')
        self.assertEqual(before,self.validate()); self.assertEqual(state.read_bytes(),b'machine state')
        with self.assertRaises(SnapshotError): self.publish()
    def test_wrong_owner_runtime_policy(self):
        self.publish()
        for args in ({'tenant':'tenant-b'},{'session':'other'},{'compatibility':{}},{'policy':{}}):
            with self.assertRaises(SnapshotError): self.validate(**args)
    def test_missing_corrupt_incomplete(self):
        self.publish(); bundle=self.store.path('s1'); bundle.chmod(0o700)
        manifest=bundle/'manifest.json'; manifest.chmod(0o600)
        m=json.loads(manifest.read_text()); m['complete']=False; manifest.write_text(json.dumps(m))
        with self.assertRaises(SnapshotError): self.validate()
        m['complete']=True; manifest.write_text(json.dumps(m))
        memory=bundle/'memory.mem'; memory.chmod(0o600); memory.write_bytes(b'corrupted')
        with self.assertRaises(SnapshotError): self.validate()
        memory.unlink()
        with self.assertRaises(SnapshotError): self.validate()
    def test_failure_after_disk_before_publish(self):
        def fail(phase):
            if phase=='after-disk': raise RuntimeError('injected interruption')
        with self.assertRaises(RuntimeError): self.publish(fail)
        with self.assertRaises(SnapshotError): self.validate()
        self.assertEqual(len(self.store.recover()),1); self.assertFalse(self.store.recover())
    def test_abrupt_process_interruption(self):
        # A separate publisher exits mid-capture or before publication; no VMM is spawned.
        code="""import os,sys
from pathlib import Path
from sandbox.snapshots import SnapshotStore
store=SnapshotStore(sys.argv[1]); disk=Path(sys.argv[2]); phase=sys.argv[3]
def capture(state,memory):
 state.write_bytes(b'machine'); memory.write_bytes(b'partial memory')
 if phase=='during-capture': os._exit(73)
def crash(name):
 if name==phase: os._exit(73)
store.publish('s1','tenant-a','session-a',{}, {},disk,capture,crash)
"""
        for phase in ('during-capture','after-capture','after-disk','after-manifest'):
            with self.subTest(phase=phase):
                p=subprocess.run([sys.executable,'-c',code,str(self.store.root),str(self.disk),phase],timeout=10)
                self.assertEqual(p.returncode,73)
                with self.assertRaises(SnapshotError): self.store.validate('s1','tenant-a','session-a',{}, {})
                self.assertEqual(len(self.store.recover()),1)
    def test_committed_bundle_survives_publisher_error(self):
        def fail(phase):
            if phase=='after-publish': raise RuntimeError('lost acknowledgement')
        with self.assertRaises(RuntimeError): self.publish(fail)
        self.validate(); self.assertEqual(self.store.recover(),[])
    def test_invalid_id_and_symlink(self):
        with self.assertRaises(SnapshotError): self.store.path('../escape')
        self.publish()
        if os.name!='nt':
            bundle=self.store.path('s1'); bundle.chmod(0o700); memory=bundle/'memory.mem'; memory.unlink(); memory.symlink_to(self.disk)
            with self.assertRaises(SnapshotError): self.validate()
